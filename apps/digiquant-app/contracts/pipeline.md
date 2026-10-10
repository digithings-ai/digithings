# Contract fragment: pipeline + strategies

All routes: `GET`, envelope `{ data, as_of, provenance }`. Types in `lib/api-pipeline.ts`.
`latest` stands in for `:date`; `default` for strategy `:id` (selection is a TODO). Null = unknown, rendered "—"; never default a number. Arrays may be empty; missing optional fields render a withheld state. State strings are open (`ok|carried|failed|running|idle|skipped|not_persisted|...`).
Source column is a best guess (dashboard-api has no pipeline/strategy code yet; BLOCKS.md lists run_health and run_event_trace tables).

| route | query | data shape | source |
|---|---|---|---|
| `/pipeline/runs/latest/health` | `date?` | `{run_date, run_type, status, config, posture, nodes?:{ok,carried,failed}, inputs_calls?:{persisted:boolean\|null, note?}, calls?, tokens_in?, tokens_out?, cost_usd?}` ; `persisted:false` is a typed gap, not a failure | `run_health` |
| `/pipeline/runs/latest/graph` | | `{run_date, selected_node, nodes:[{id,label,stage,col:number,state?,to?:string[]}]}` ; `col` orders stage columns | node/run tables (`run_event_trace`) |
| `/pipeline/runs/latest/nodes/selected/document` | `node?` | `{run_date,node_id,title,paragraphs?:string[],note?}` ; "selected" = server default node (daily digest) until client selection exists | node artifacts |
| `/pipeline/runs/latest/narrative` | | `{run_date,heading,paragraphs?:string[]}` | /why narrative |
| `/pipeline/runs/latest/trace` | | `{rows:[{node,calls:number\|null,duration_s:number\|null,state}]}` ; null calls/duration = not persisted | `run_event_trace` |
| `/pipeline/runs/latest/artifacts` | | `{rows:[{stage,node,document:string\|null,date,state_only?:boolean}]}` ; `document:null`+`state_only` = node wrote state, no document | artifact registry |
| `/strategies/summary` | | `{catalog,deployable,deployments,paper_accounts,portfolios,brokers: number\|null, plan, last_run: string\|null, notice?:{tag:'soon'\|'wip',text}}` | strategies catalog (new) |
| `/strategies` | | `{strategies:[{id,name,family,universe,cadence,targets:string[]\|null,status,deploy}]}` | catalog |
| `/strategies/deployments` | | `{deployments:[{id,strategy_id,target,status,last_run}], empty_reason?}` | deployments |
| `/strategies/targets` | | `{targets:[{target,description,status}]}` | static config |
| `/strategies/default` | | `{id,name,lede,family,universe,cadence,targets,related_thesis,execution}` (all string\|null) | catalog |
| `/strategies/default/parameters` | | `{parameters:[{name,value:string\|number\|null,state}]}` | strategy config |
| `/strategies/default/performance` | | `{available:boolean, reason?, points?:[{date,value:number\|null}]}` ; `available:false` renders "Not available", nothing estimated | deployment NAV |
| `/strategies/default/runs` | | `{runs:[{run_date,status,deployment_id}], empty_reason?}` | deployment runs |
| `/strategies/deploy-flow` | | `{steps:[{label,detail,state:'done'\|'active'\|'todo'\|'failed',status}]}` | static config |
| `/strategies/default/deploy-draft` | | `{target_kind,paper_capital,broker,portfolio,schedule, notice?}` | draft config |

Writes: none wired. Planned `POST /strategies/:id/deployments` (BLOCKS.md "not built"); mock returns 201 / 422 for it; no block calls it yet (would sit inside st-deploy-draft with its own result/error text).
