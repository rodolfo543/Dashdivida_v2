# Dashboard de Dívida - AXS Energia

Este pacote já está pronto para ser publicado no GitHub e no GitHub Pages.

## Estrutura principal

- `dashboard_server.py`: motor que lê os scripts Python e monta os payloads do dashboard
- `servidor_dashboard.py`: gerador estático e preview local
- `dashhtml.html`, `dashboard.css`, `dashboard.js`: frontend
- `Code final prontos/`: scripts Python das operações
- `docs/`: site estático pronto para GitHub Pages
- `data/`: JSONs gerados localmente
- `.github/workflows/update-dashboard.yml`: atualização automática

## Operações incluídas

- `AXS 02`
- `AXS 03`
- `AXS 04`
- `AXS 05`
- `AXS 06`
- `AXS 07`
- `AXS 08`
- `AXS 09`
- `AXS 10`
- `AXS 11`

## Como testar localmente

Na pasta `Novo dashboard`, rode:

```powershell
python .\servidor_dashboard.py serve
```

Depois abra:

```text
http://127.0.0.1:8000
```

## Como regenerar os arquivos estáticos

```powershell
python .\servidor_dashboard.py build
```

Isso atualiza:

- `docs/`
- `data/`
- `index.html`

## Como publicar no GitHub

1. Crie o repositório `Dashdivida_v2`
2. Envie todo o conteúdo da pasta `Novo dashboard`
3. Em `Settings > Pages`
4. Escolha `Deploy from a branch`
5. Selecione a branch principal
6. Selecione a pasta `/docs`
7. Salve

## Atualização automática

O workflow do GitHub Actions:

- atualiza semanalmente
- atualiza todo dia `13`
- também permite execução manual em `Actions`

## Observação

Os scripts `AXS 06` e `AXS 11` usam a data de início da rentabilidade como premissa operacional, conforme já documentado em seus próprios arquivos. Se a primeira integralização oficial mudar, basta ajustar o script correspondente e rodar o build novamente.
