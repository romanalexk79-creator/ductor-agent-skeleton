# Operations

## Config changes

Edit only the requested keys in `config/config.json`, then restart:
```bash
touch ~/.ductor/restart-requested
```

## Cron

- List:   `python3 tools/cron_tools/cron_list.py`
- Add:    `python3 tools/cron_tools/cron_add.py ...`
- Edit:   `python3 tools/cron_tools/cron_edit.py ...`
- Remove: `python3 tools/cron_tools/cron_remove.py ...`
- Check timezone before scheduling: `python3 tools/cron_tools/cron_time.py`

Never hand-edit `cron_jobs.json`.

## Webhooks

`python3 tools/webhook_tools/webhook_{list,add,edit,remove,test}.py`

## Background tasks

`python3 tools/task_tools/{create,cancel,resume,list}_task.py`

## Sub-agents

`python3 tools/agent_tools/{list_agents,ask_agent,ask_agent_async,create_agent,remove_agent}.py`

## Notifications

`python3 tools/user_tools/notify.py "message"` — fans out to allowed chat ids.

## Backups

Not configured in the skeleton. Add host-side backups of `~/.ductor` state
(sessions, cron/webhook registries, memory) before going to production.
