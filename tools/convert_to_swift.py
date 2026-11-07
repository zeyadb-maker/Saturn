#!/usr/bin/env python3
"""Convert repository C/C++ and functional Python sources into .swift files."""
from __future__ import annotations
import argparse, ast, concurrent.futures, json, os, re, sys, time
from collections import defaultdict
from pathlib import Path
import requests

EXTS={".c",".cc",".cpp",".cxx",".h",".hh",".hpp",".hxx",".inl",".ipp",".tpp",".py"}
IGNORE={".git",".github",".build","build","dist","node_modules",".idea",".vscode","SwiftPort","__pycache__",".venv","venv"}
NAME_SKIP=re.compile(r"(^|[_-])(extract|extractor|unpack|unpacker|decompile|asset_dump|dump_assets)([_-]|$)",re.I)
CODE_SKIP=re.compile(r"\b(extractall|extractfile|unpack_archive|decompile|dump_assets|extract_(?:texture|model|asset|audio|sound|image|resource))\b",re.I)

SYSTEM="""Translate the supplied C, C++, or Python source into real Swift. Preserve algorithms,
behavior, control flow, names, and comments. Use idiomatic Swift and Foundation.
Do not output Python, C, C++, pseudocode, or Markdown fences. Do not omit logic.
Saturn uses SDL2 for graphics, audio, and input. Preserve SDL2 behavior and event,
rendering, and audio semantics. Do not silently replace SDL2 with SDL3 or invent Swift
SDL APIs. When SDL2 C APIs need an interop layer, create a clearly named SDL2Bridge
boundary and mark the exact bridging work required. Keep original SDL symbol names
in comments. Mark unavailable external APIs with TODO adapters, not invented APIs.
Input may be a fragment: translate every supplied line. Return code only."""

def py_ok(path,src):
    if NAME_SKIP.search(path.stem): return False,"filename indicates extraction/unpacking"
    try: tree=ast.parse(src)
    except SyntaxError: return False,"not valid Python syntax"
    logic=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.If,ast.For,ast.AsyncFor,ast.While,ast.With,ast.AsyncWith,ast.Try,ast.Expr,ast.Assign,ast.AnnAssign))]
    if not logic: return False,"no executable program logic"
    funcs=[n.name.lower() for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    extract_funcs=sum(any(w in n for w in ("extract","unpack","decompile","dump_asset")) for n in funcs)
    calls=len(CODE_SKIP.findall(src)); archives=len(re.findall(r"\b(zipfile|tarfile|unpack_archive|extractall)\b",src,re.I))
    if extract_funcs and extract_funcs>=max(1,len(funcs)//2): return False,"main Python functions extract/unpack data"
    if calls>=2 or (archives>=2 and calls>=1): return False,"Python script primarily extracts/unpacks data"
    return True,"functional Python logic"

def discover(root):
    files=[]; skipped=[]
    for cur,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in IGNORE and not d.startswith(".")]
        for name in names:
            p=Path(cur)/name
            if p.suffix.lower() not in EXTS: continue
            try: src=p.read_text(encoding="utf-8",errors="replace")
            except OSError as e:
                skipped.append({"source":str(p.relative_to(root)),"reason":str(e)}); continue
            if p.suffix.lower()==".py":
                ok,why=py_ok(p,src)
                if not ok:
                    skipped.append({"source":str(p.relative_to(root)),"reason":why}); continue
            files.append(p)
    return sorted(files),skipped

def output_paths(files,root,out):
    # Replace the original extension with .swift. If two source files share the
    # same path stem (for example foo.c and foo.h), suffix only those collisions.
    groups=defaultdict(list)
    for p in files:
        rel=p.relative_to(root)
        groups[str((out/rel).with_suffix(".swift"))].append(p)
    mapping={}
    for base,items in groups.items():
        for p in items:
            rel=p.relative_to(root)
            dest=(out/rel).with_suffix(".swift")
            if len(items)>1:
                dest=dest.with_name(dest.stem+"_"+p.suffix.lstrip(".")+".swift")
            mapping[p]=dest
    return mapping

def chunks(src,limit):
    result=[]; current=[]; size=0
    for line in src.splitlines(keepends=True):
        if current and size+len(line)>limit:
            result.append("".join(current)); current=[]; size=0
        current.append(line); size+=len(line)
    if current: result.append("".join(current))
    return result or [""]

def call_model(session,url,model,fragment,path,part,total,timeout,retries):
    prompt=f"Original path: {path}\nFragment {part}/{total}. Translate every line to Swift and preserve all logic.\n\nSOURCE:\n{fragment}"
    # /api/generate avoids chat-template compatibility problems across Ollama builds.
    payload={"model":model,"prompt":SYSTEM+"\n\n"+prompt,"stream":False,
             "options":{"temperature":0.1,"num_ctx":4096}}
    last=None
    for attempt in range(retries+1):
        try:
            started=time.monotonic()
            r=session.post(url,json=payload,timeout=(15,timeout))
            if not r.ok:
                detail=r.text[:2000].replace("\n"," ")
                raise RuntimeError(f"Ollama HTTP {r.status_code}: {detail}")
            data=r.json()
            answer=data.get("response","").strip()
            if not answer: raise RuntimeError(f"empty Ollama response: {str(data)[:1000]}")
            return answer+"\n",time.monotonic()-started
        except Exception as e:
            last=e
            if attempt<retries: time.sleep(min(2**attempt,10))
    raise RuntimeError(f"Ollama request failed after {retries+1} attempt(s): {last}")

def convert_one(item,root,outputs,args):
    i,total,p=item; dest=outputs[p]; rel=p.relative_to(root)
    model=args.models[(i-1)%len(args.models)]
    dest.parent.mkdir(parents=True,exist_ok=True); started=time.monotonic()
    try:
        parts=chunks(p.read_text(encoding="utf-8",errors="replace"),args.chunk_chars)
        with requests.Session() as session:
            result=[]; model_seconds=0.0
            for n,part in enumerate(parts,1):
                print(f"[{i}/{total}] {rel} — chunk {n}/{len(parts)} started",flush=True)
                translated,elapsed=call_model(session,args.endpoint,model,part,str(rel),n,len(parts),args.timeout,args.retries)
                result.append(translated); model_seconds+=elapsed
                print(f"[{i}/{total}] {rel} — chunk {n}/{len(parts)} returned in {elapsed:.1f}s",flush=True)
        dest.write_text("\n".join(result),encoding="utf-8")
        return {"ok":True,"record":{"source":str(rel),"output":str(dest.relative_to(root)),"chunks":len(parts),"model_seconds":round(model_seconds,1),"total_seconds":round(time.monotonic()-started,1)}}
    except Exception as e:
        safe_error=str(e).replace("\n"," ").replace("\r"," ").replace("*/","* /")
        dest.write_text("// CONVERSION FAILED — manual Swift port required.\n"+f"// Original source: {rel}\n"+f"// Reason: {safe_error}\n",encoding="utf-8")
        return {"ok":False,"record":{"source":str(rel),"output":str(dest.relative_to(root)),"error":str(e),"total_seconds":round(time.monotonic()-started,1)}}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path.cwd()); ap.add_argument("--output",default="SwiftPort")
    ap.add_argument("--model",default=os.getenv("OLLAMA_MODEL","qwen2.5-coder:3b"),help="Fallback single model")
    ap.add_argument("--models",default=os.getenv("OLLAMA_MODELS",""),help="Comma-separated Ollama models; files are distributed round-robin")
    ap.add_argument("--endpoint",default="http://127.0.0.1:11434/api/generate")
    ap.add_argument("--chunk-chars",type=int,default=3000); ap.add_argument("--timeout",type=int,default=240)
    ap.add_argument("--retries",type=int,default=2); ap.add_argument("--workers",type=int,default=2)
    a=ap.parse_args(); a.models=[m.strip() for m in a.models.split(",") if m.strip()] or [a.model]; root=a.root.resolve(); out=(root/a.output).resolve()
    if not root.is_dir(): ap.error("repository root does not exist")
    if a.workers<1: ap.error("--workers must be at least 1")
    files,skipped=discover(root); outputs=output_paths(files,root,out); out.mkdir(parents=True,exist_ok=True)
    print(f"Found {len(files)} source files; output names end in .swift only. Models={a.models}; workers={a.workers}.",flush=True)
    done=[]; failed=[]; total=len(files)
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(convert_one,(i,total,p),root,outputs,a) for i,p in enumerate(files,1)]
        for future in concurrent.futures.as_completed(futures):
            result=future.result()
            if result["ok"]:
                done.append(result["record"])
                print(f"COMPLETED {result['record']['source']} — {len(done)}/{total}",flush=True)
            else:
                failed.append(result["record"])
                print(f"FAILED {result['record']['source']}: {result['record']['error']}",file=sys.stderr,flush=True)
    report={"candidate_count":total,"translated_count":len(done),"failed_count":len(failed),"skipped_count":len(skipped),
            "translated":sorted(done,key=lambda x:x["source"]),"failed":sorted(failed,key=lambda x:x["source"]),
            "skipped":skipped,"mapping":"Original extension replaced with .swift; same-directory basename collisions receive a short source-extension suffix."}
    (out/"conversion_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"SUMMARY translated={len(done)} failed={len(failed)} skipped={len(skipped)}",flush=True)
    return 0 if done else 2

if __name__=="__main__": raise SystemExit(main())
