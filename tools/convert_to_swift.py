#!/usr/bin/env python3
"""Repository-wide C/C++ and functional Python to Swift migration mirror.

Every source gets its own .swift output while preserving its original extension
(e.g. foo.c.swift and foo.h.swift), preventing same-basename overwrites.
"""
from __future__ import annotations
import argparse, ast, concurrent.futures, json, os, re, sys, time
from pathlib import Path
import requests

EXTS={".c",".cc",".cpp",".cxx",".h",".hh",".hpp",".hxx",".inl",".ipp",".tpp",".py"}
IGNORE={".git",".github",".build","build","dist","node_modules",".idea",".vscode","SwiftPort","__pycache__",".venv","venv"}
NAME_SKIP=re.compile(r"(^|[_-])(extract|extractor|unpack|unpacker|decompile|asset_dump|dump_assets)([_-]|$)",re.I)
CODE_SKIP=re.compile(r"\b(extractall|extractfile|unpack_archive|decompile|dump_assets|extract_(?:texture|model|asset|audio|sound|image|resource))\b",re.I)

SYSTEM="""Translate supplied C, C++, or Python source into real Swift. Preserve algorithms,
behavior, control flow, names, and comments. Use idiomatic Swift/Foundation.
Do not output Python, C, C++, pseudocode, or Markdown fences. Do not omit logic.
For unavailable external APIs, add clearly marked TODO adapters/comments instead
of inventing APIs. Input may be a fragment: translate every supplied line.
Return code only."""

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

def discover(root,out):
    files=[]; skipped=[]
    for cur,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in IGNORE and not d.startswith(".")]
        for name in names:
            p=Path(cur)/name
            if p.suffix.lower() not in EXTS: continue
            try: p.relative_to(out); continue
            except ValueError: pass
            try: src=p.read_text(encoding="utf-8",errors="replace")
            except OSError as e:
                skipped.append({"source":str(p.relative_to(root)),"reason":str(e)}); continue
            if p.suffix.lower()==".py":
                ok,why=py_ok(p,src)
                if not ok:
                    skipped.append({"source":str(p.relative_to(root)),"reason":why}); continue
            files.append(p)
    return sorted(files),skipped

def chunks(src,limit):
    out=[]; cur=[]; size=0
    for line in src.splitlines(keepends=True):
        if cur and size+len(line)>limit:
            out.append("".join(cur)); cur=[]; size=0
        cur.append(line); size+=len(line)
    if cur: out.append("".join(cur))
    return out or [""]

def call_model(session,url,model,fragment,path,part,total,timeout,retries):
    prompt=f"Original path: {path}\nFragment {part}/{total}. Translate every line to Swift and preserve all logic.\n\nSOURCE:\n{fragment}"
    payload={"model":model,"stream":False,"keep_alive":"-1","messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"options":{"temperature":0.1,"num_ctx":8192}}
    last=None
    for attempt in range(retries+1):
        try:
            started=time.monotonic()
            r=session.post(url,json=payload,timeout=(15,timeout)); r.raise_for_status()
            answer=r.json()["message"]["content"].strip()
            if not answer: raise RuntimeError("empty model response")
            return answer+"\n",time.monotonic()-started
        except Exception as e:
            last=e
            if attempt<retries: time.sleep(min(2**attempt,10))
    raise RuntimeError(f"Ollama request failed after {retries+1} attempt(s): {last}")

def convert_one(item,root,out,args):
    i,total,p=item
    rel=p.relative_to(root); dest=out / (str(rel) + ".swift")
    dest.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    try:
        parts=chunks(p.read_text(encoding="utf-8",errors="replace"),args.chunk_chars)
        session=requests.Session(); result=[]; model_seconds=0.0
        for n,part in enumerate(parts,1):
            print(f"[{i}/{total}] {rel} — chunk {n}/{len(parts)} started",flush=True)
            translated,elapsed=call_model(session,args.endpoint,args.model,part,str(rel),n,len(parts),args.timeout,args.retries)
            result.append(translated); model_seconds+=elapsed
            print(f"[{i}/{total}] {rel} — chunk {n}/{len(parts)} returned in {elapsed:.1f}s",flush=True)
        dest.write_text("\n".join(result),encoding="utf-8")
        return {"ok":True,"record":{"source":str(rel),"output":str(dest.relative_to(root)),"chunks":len(parts),"model_seconds":round(model_seconds,1),"total_seconds":round(time.monotonic()-started,1)}}
    except Exception as e:
        return {"ok":False,"record":{"source":str(rel),"error":str(e),"total_seconds":round(time.monotonic()-started,1)}}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path.cwd()); ap.add_argument("--output",default="SwiftPort")
    ap.add_argument("--model",default=os.getenv("OLLAMA_MODEL","qwen2.5-coder:3b"))
    ap.add_argument("--endpoint",default="http://localhost:11434/api/chat")
    ap.add_argument("--chunk-chars",type=int,default=3500); ap.add_argument("--timeout",type=int,default=240)
    ap.add_argument("--retries",type=int,default=0); ap.add_argument("--workers",type=int,default=2)
    ap.add_argument("--overwrite",action="store_true")
    a=ap.parse_args(); root=a.root.resolve(); out=(root/a.output).resolve()
    if not root.is_dir(): ap.error("repository root does not exist")
    if a.workers<1: ap.error("--workers must be at least 1")
    out.mkdir(parents=True,exist_ok=True); files,skipped=discover(root,out)
    pending=[]; total=len(files)
    for i,p in enumerate(files,1):
        rel=p.relative_to(root); dest=out / (str(rel) + ".swift")
        if dest.exists() and not a.overwrite:
            skipped.append({"source":str(rel),"reason":"output already exists"})
        else: pending.append((i,total,p))
    print(f"Found {total} files; {len(pending)} queued, excluded {len(skipped)} Python/data utilities. Model={a.model}; workers={a.workers}; timeout={a.timeout}s.",flush=True)
    done=[]; failed=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(convert_one,item,root,out,a) for item in pending]
        for future in concurrent.futures.as_completed(futures):
            result=future.result()
            if result["ok"]:
                done.append(result["record"])
                print(f"COMPLETED {result['record']['source']} ({result['record']['total_seconds']}s) — {len(done)}/{len(pending)} finished",flush=True)
            else:
                failed.append(result["record"])
                print(f"FAILED {result['record']['source']}: {result['record']['error']}",file=sys.stderr,flush=True)
    report={"candidate_count":total,"queued_count":len(pending),"translated_count":len(done),"failed_count":len(failed),"skipped_count":len(skipped),"translated":sorted(done,key=lambda x:x["source"]),"failed":sorted(failed,key=lambda x:x["source"]),"skipped":skipped,"mapping":"Each source is mirrored as <original filename>.swift, preserving the original extension to avoid .c/.h basename collisions.","note":"AI output needs manual API/interoperability and compile review. Failed files are listed explicitly; the workflow continues to package partial output."}
    (out/"conversion_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"SUMMARY translated={len(done)} failed={len(failed)} skipped={len(skipped)}",flush=True)
    return 0

if __name__=="__main__": raise SystemExit(main())
