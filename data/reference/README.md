# Limites geográficos de referência

`distritos_sp.geojson` contém os 96 distritos municipais de São Paulo, baixados do serviço oficial GeoSampa (camada `geoportal:distrito_municipal`, em SIRGAS 2000 / EPSG:4326). O arquivo é usado como geometria de referência; as contagens vêm dos registros SSP-SP com coordenadas que caem dentro de cada distrito.

Fonte: [GeoSampa — metadados da camada Distrito](https://metadados.geosampa.prefeitura.sp.gov.br/geonetwork/srv/api/records/51f75eab-6d90-451e-9f80-c21c1ac72630). A plataforma indica licença CC BY-SA para as camadas geoespaciais produzidas pela Prefeitura; preserve esta atribuição ao redistribuir o arquivo.

Para carregar os limites no PostGIS local, depois de configurar `.env`, execute:

```powershell
python scripts/importar_distritos_sp.py
```

O script pode ser executado novamente para atualizar os limites. Depois de importar/atualizar os CSVs, gere novamente o resumo rápido do mapa:

```powershell
python scripts/atualizar_resumo_distritos.py
```
