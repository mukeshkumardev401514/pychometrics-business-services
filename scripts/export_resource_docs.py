"""Generate table coverage and Postman requests from the registered OpenAPI routes."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
with patch('psycopg_pool.ConnectionPool'):
    from app.main import app
from app.resources.models import CATALOG
from app.resources.policy import POLICIES, READ_ONLY

schema = app.openapi()
lines = ['# Database resource API coverage', '',
         'Generated with `python scripts/export_resource_docs.py`. Every table is listed below.', '',
         'Platform token: `/platform/auth/login`. Tenant token: `/auth/login`.',
         'Keys are UUIDs, except migration versions and comma-separated composite keys in the listed order.', '',
         '| Database | Table | Key | Administrative operations | Tenant operations | Source |',
         '| --- | --- | --- | --- | --- | --- |']
for scope,tables in CATALOG.items():
    for name,spec in tables.items():
        slug=name.replace('_','-')
        prefix='/platform/data' if scope=='platform' else '/platform/tenants/{tenant_id}/data'
        def ops(path):
            return ', '.join(m.upper() for m in ('post','get','patch','delete') if m in schema['paths'].get(path,{}) or m in schema['paths'].get(path+'/{key}',{})) or '—'
        lines.append(f'| {scope} | `{name}` | `{",".join(spec["primary_key"])}` | {ops(prefix+"/"+slug)} | {ops("/data/"+slug) if scope=="tenant" else "—"} | `{spec["source"]}` |')
lines += ['', 'GET includes list and detail. DELETE archives doctor/patient profiles and refuses referenced records.',
          'Platform assessment catalog, tenants, payments and tenant assignments have DELETE routes that return 409; use status updates because their cross-database references cannot cascade safely.',
          'History, migration bookkeeping and authentication challenge tables are read-only. Existing doctor/patient creation routes retain their transactional behavior.',
          'Tenant methods additionally enforce role, permission and ownership checks; see `docs/resource-api.md`.', '',
          '## Migration file inventory', '', '| File | Tables declared |', '| --- | --- |']
for path in sorted((ROOT/'psychometric-db-models').rglob('*.sql')):
    names=[f'{scope}.{name}' for scope,tables in CATALOG.items() for name,spec in tables.items() if spec['source']==str(path.relative_to(ROOT))]
    lines.append(f'| `{path.relative_to(ROOT)}` | {", ".join(names) or "Enums, extension, alteration or seed data; no separate table endpoint"} |')
(ROOT/'docs/database-api-coverage.md').write_text('\n'.join(lines)+'\n')

collection_path=ROOT/'postman/psychometrics-all-apis.postman_collection.json'
collection=json.loads(collection_path.read_text())
collection['item']=[folder for folder in collection['item'] if folder['name'] not in {'Platform authentication','Platform resources','Tenant maintenance resources','Tenant resource APIs'}]
variables={v['key']:v for v in collection['variable']}
for key,value in {'platform_email':'','platform_password':'','platform_token':'','maintenance_tenant_id':'', 'resource_token':''}.items():
    variables.setdefault(key,{'key':key,'value':value,'type':'string'})


def example(prop,name):
    if '$ref' in prop: return example(schema['components']['schemas'][prop['$ref'].split('/')[-1]],name)
    if 'anyOf' in prop: return example(next(p for p in prop['anyOf'] if p.get('type')!='null'),name)
    if 'enum' in prop: return prop['enum'][0]
    if name=='email': return 'example@example.com'
    if name=='password': return '{{platform_password}}'
    if prop.get('format')=='uuid':
        key='ref_'+name
        variables.setdefault(key,{'key':key,'value':'','type':'string'})
        return '{{'+key+'}}'
    if prop.get('format')=='date-time': return '2026-09-16T10:00:00Z'
    if prop.get('format')=='date': return '2026-09-16'
    if prop.get('format')=='time': return '09:00:00'
    if prop.get('type') in ('integer','number'): return 1
    if prop.get('type')=='boolean': return True
    if name in {'metadata','setting_value','payload','event_data'}: return {}
    return 'example'


def item(method,path,operation,token,scope=None,table=None):
    url='{{base_url}}'+path.replace('{tenant_id}','{{maintenance_tenant_id}}')
    if '{key}' in url:
        var=f'{scope}_{table}_key'
        variables.setdefault(var,{'key':var,'value':'','type':'string'})
        url=url.replace('{key}','{{'+var+'}}')
    req={'method':method.upper(),'url':url,'auth':{'type':'bearer','bearer':[{'key':'token','value':'{{'+token+'}}','type':'string'}]},'header':[],
         'description':operation.get('description','')+' Examples are templates: replace IDs with related records and satisfy documented database constraints. PATCH/DELETE mutate records; do not run the entire collection blindly.'}
    if 'requestBody' in operation:
        model=operation['requestBody']['content']['application/json']['schema']
        if '$ref' in model: model=schema['components']['schemas'][model['$ref'].split('/')[-1]]
        props=model.get('properties',{})
        fields=model.get('required',[]) if method=='post' else [next((k for k in props if k not in {'password','user_id'} and not k.endswith('_id')), next(iter(props),'description'))]
        body={name:example(props[name],name) for name in fields}
        req['header']=[{'key':'Content-Type','value':'application/json'}]
        req['body']={'mode':'raw','raw':json.dumps(body,indent=2),'options':{'raw':{'language':'json'}}}
    result={'name':operation.get('summary',method.upper()+' '+path),'request':req,'response':[]}
    if method=='post' and table:
        keys=CATALOG[scope][table]['primary_key']
        var=f'{scope}_{table}_key'
        variables.setdefault(var,{'key':var,'value':'','type':'string'})
        result['event']=[{'listen':'test','script':{'type':'text/javascript','exec':['if (pm.response.code === 201) { const data = pm.response.json();', f'pm.collectionVariables.set("{var}", {json.dumps(keys)}.map(k => data[k]).join(","));', '}']}}]
    return result

login=item('post','/platform/auth/login',schema['paths']['/platform/auth/login']['post'],'platform_token')
login['request']['auth']={'type':'noauth'}
login['request']['body']['raw']=json.dumps({'email':'{{platform_email}}','password':'{{platform_password}}'},indent=2)
login['event']=[{'listen':'test','script':{'type':'text/javascript','exec':['pm.collectionVariables.unset("platform_token");','if (pm.response.code === 200) pm.collectionVariables.set("platform_token", pm.response.json().access_token);']}}]
collection['item'].append({'name':'Platform authentication','item':[login,item('get','/platform/auth/me',schema['paths']['/platform/auth/me']['get'],'platform_token')]})
for folder_name,scope,prefix,token in [('Platform resources','platform','/platform/data','platform_token'),('Tenant maintenance resources','tenant','/platform/tenants/{tenant_id}/data','platform_token'),('Tenant resource APIs','tenant','/data','resource_token')]:
    groups=[]
    for table in CATALOG[scope]:
        path=prefix+'/'+table.replace('_','-')
        requests=[]
        for suffix in ('','/{key}'):
            for method,operation in schema['paths'].get(path+suffix,{}).items():
                if method in ('get','post','patch','delete'):
                    requests.append(item(method,path+suffix,operation,token,scope,table))
        if requests: groups.append({'name':table,'item':requests})
    collection['item'].append({'name':folder_name,'item':groups})
# The last successful tenant login selects the token for tenant resource APIs.
for folder in collection['item']:
    for entry in folder.get('item', []):
        req = entry.get('request', {})
        if req.get('url') != '{{base_url}}/auth/login':
            continue
        body = json.loads(req['body']['raw'])
        role = body['email'].replace('{{', '').replace('_email}}', '')
        token = role + '_token'
        script = entry['event'][0]['script']['exec']
        script[:] = [line for line in script if 'resource_token' not in line]
        script.insert(0, 'pm.collectionVariables.unset("resource_token");')
        script.append(f'if (pm.response.code === 200 && pm.collectionVariables.get("{token}")) pm.collectionVariables.set("resource_token", pm.collectionVariables.get("{token}"));')
variables['resource_token']['value'] = ''
collection['variable']=list(variables.values())
collection['info']['description']='All existing workflows plus schema-backed table APIs. Platform resources and tenant maintenance require a separate platform token. Tenant resource_token is saved by the last successful tenant login; log in with the appropriate role before using tenant resources. Read docs/resource-api.md and docs/database-api-coverage.md before running write requests.'
collection_path.write_text(json.dumps(collection,indent=2,ensure_ascii=False)+'\n')
print('Exported coverage and collection:',len(schema['paths']),'paths')
