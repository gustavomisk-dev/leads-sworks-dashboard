# leads-sworks-dashboard

Dashboard da esteira de leads SWorks, hospedado no Streamlit Community Cloud.
Dados lidos do repositorio privado `leads-sworks-data` via GitHub API.

## Secrets necessarios

Configure em **Settings > Secrets** no painel do Streamlit Community Cloud:

```toml
[github]
token = "ghp_..."
repo = "gustavomisk-dev/leads-sworks-data"
```

## Deploy

1. Conecte este repositorio em [share.streamlit.io](https://share.streamlit.io)
2. Main file: `app.py`
3. Adicione os secrets acima
4. Deploy
