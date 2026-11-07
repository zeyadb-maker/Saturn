#!/usr/bin/env python3
"""Repository-wide best-effort C/C++ and functional Python to Swift converter."""
from __future__ import annotations
import argparse, ast, json, os, re, sys, time
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
            except OSError as e: skipped.append({"source":str(p.relative_to(root)),"reason":str(e)}); continue
            if p.suffix.lower()==".py":
                ok,why=py_ok(p,src)
                if not ok: skipped.append({"source":str(p.relative_to(root)),"reason":why}); continue
            files.append(p)
    return sorted(files),skipped
def chunks(src,limit):
    out=[]; cur=[]; size=0
    for line in src.splitlines(keepends=True):
        if cur and size+len(line)>limit: out.append("".join(cur));cur=[];size=0
        cur.append(line);size+=len(line)
    if cur: out.append("".join(cur))
    return out or [""]
def call_model(s,url,model,fragment,path,part,total,timeout,retries):
    prompt=f"Original path: {path}\nFragment {part}/{total}. Translate every line to Swift and preserve all logic.\n\nSOURCE:\n{fragment}"
    payload={"model":model,"stream":False,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"options":{"temperature":0.1,"num_ctx":16384}}
    last=None
    for attempt in range(retries+1):
        try:
            r=s.post(url,json=payload,timeout=timeout);r.raise_for_status()
            answer=r.json()["message"]["content"].strip()
            if not answer: raise RuntimeError("empty model response")
            return answer+"\n"
        except Exception as e:
            last=e
            if attempt<retries: time.sleep(min(2**attempt,20))
    raise RuntimeError(f"Ollama request failed: {last}")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path.cwd());ap.add_argument("--output",default="SwiftPort")
    ap.add_argument("--model",default=os.getenv("OLLAMA_MODEL","qwen2.5-coder:7b"))
    ap.add_argument("--endpoint",default="http://localhost:11434/api/chat")
    ap.add_argument("--chunk-chars",type=int,default=9000);ap.add_argument("--timeout",type=int,default=1800)
    ap.add_argument("--retries",type=int,default=2);ap.add_argument("--overwrite",action="store_true")
    a=ap.parse_args();root=a.root.resolve();out=(root/a.output).resolve()
    if not root.is_dir(): ap.error("repository root does not exist")
    out.mkdir(parents=True,exist_ok=True);files,skipped=discover(root,out)
    print(f"Found {len(files)} files; excluded {len(skipped)} Python/data utilities.",flush=True)
    s=requests.Session();done=[];failed=[]
    for i,p in enumerate(files,1):
        rel=p.relative_to(root);dest=(out/rel).with_suffix(".swift");dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and not a.overwrite:
            skipped.append({"source":str(rel),"reason":"output already exists"});continue
        print(f"[{i}/{len(files)}] {rel}",flush=True)
        try:
            parts=chunks(p.read_text(encoding="utf-8",errors="replace"),a.chunk_chars);result=[]
            for n,part in enumerate(parts,1):
                print(f"  chunk {n}/{len(parts)}",flush=True)
                result.append(call_model(s,a.endpoint,a.model,part,str(rel),n,len(parts),a.timeout,a.retries))
            dest.write_text("\n".join(result),encoding="utf-8")
            done.append({"source":str(rel),"output":str(dest.relative_to(root)),"chunks":len(parts)})
        except Exception as e: failed.append({"source":str(rel),"error":str(e)});print(f"FAILED: {e}",file=sys.stderr,flush=True)
    report={"candidate_count":len(files),"translated_count":len(done),"failed_count":len(failed),"skipped_count":len(skipped),"translated":done,"failed":failed,"skipped":skipped,"note":"AI output needs manual API/interoperability and compile review."}
    (out/"conversion_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"SUMMARY translated={len(done)} failed={len(failed)} skipped={len(skipped)}",flush=True)
    return 1 if failed else 0
if __name__=="__main__": raise SystemExit(main())
