import yaml,json,sys
d=yaml.safe_load(sys.stdin)
def f(x):
  if isinstance(x,dict):
    for k,v in x.items():
      if k=="DIGI_TENANT_CORPUS_MAP": return v
      r=f(v)
      if r: return r
  if isinstance(x,list):
    for v in x:
      r=f(v)
      if r: return r
print(f(d),end="")
