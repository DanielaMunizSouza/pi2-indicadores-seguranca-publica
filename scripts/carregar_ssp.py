import argparse
import csv
import getpass
import hashlib
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from progresso import Progresso, ProgressoRemoto  # noqa: E402

COLUMNS = [
    'arquivo_origem','linha_origem','categoria_dado','municipio','ano_bo',
    'data_ocorrencia','hora_ocorrencia','cep','bairro','logradouro','numero_logradouro',
    'latitude','longitude','natureza','rubrica','tipo_objeto','subtipo_objeto',
    'marca_objeto','tipo_local','modo_objeto','tipo_entorpecente','quantidade',
    'unidade_quantidade','num_bo','id_delegacia','cod_ibge','dados_originais'
]
# Dados pessoais identificáveis que não são necessários aos indicadores (LGPD): não vão ao JSONB.
CAMPOS_PESSOAIS = {'PLACA_VEICULO', 'DATA_NASCIMENTO_PESSOA', 'PROFISSAO', 'DESCR_PROFISSAO', 'NUM_CHASSI'}
# A SSP preenche o campo ausente com 'NULL' e oculta endereços de crimes sensíveis.
AUSENTES = {'', 'NULL', 'NONE', 'NAN'}
ENDERECO_OCULTO = 'VEDAÇÃO DA DIVULGAÇÃO'
COPY_SQL = 'COPY public.registro_ocorrencia (' + ','.join(COLUMNS) + ') FROM STDIN'


def first(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and value.strip().upper() not in AUSENTES:
            return value.strip()
    return None


def parsed_date(value):
    if not value:
        return None
    value = value.strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def parsed_time(value):
    if not value:
        return None
    for fmt in ('%H:%M:%S', '%H:%M', '%H:%M:%S.%f'):
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            pass
    return None


def parsed_decimal(value):
    if not value:
        return None
    value = value.strip().replace(',', '.')
    try:
        number = Decimal(value)
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def parsed_coord(value, low, high):
    number = parsed_decimal(value)
    if number is None or number < low or number > high:
        return None
    return float(number)


def valid_point(lat, lon):
    """A SSP grava 0 quando não há coordenada; no estado de SP nenhuma coordenada válida é 0."""
    if lat is None or lon is None or lat == 0 or lon == 0:
        return None, None
    return lat, lon


def hidden_address(value):
    return None if value and value.upper().startswith(ENDERECO_OCULTO) else value


def clean_cep(value):
    if not value:
        return None
    digits = re.sub(r'\D', '', value)
    if 6 <= len(digits) < 8:  # os XLSX da SSP guardam o CEP como número e perdem o zero à esquerda
        digits = digits.zfill(8)
    return digits if len(digits) == 8 and digits != '00000000' else None


def clean_municipio(value):
    if not value:
        return None
    sem_acento = ''.join(c for c in unicodedata.normalize('NFD', value.upper()) if unicodedata.category(c) != 'Mn')
    normalized = re.sub(r'[^A-Z]', '', sem_acento)
    if normalized in ('SAOPAULO', 'SPAULO'):  # a SSP abrevia como 'S.PAULO'
        return 'São Paulo'
    return value


CATEGORIAS = [  # ordem importa: o primeiro trecho encontrado no nome do arquivo vence
    ('ENTORPECENTES_GRAMAS', 'entorpecentes_gramas'),
    ('APREENSAO_DE_ENTORPECENTE', 'apreensao_entorpecente'),
    ('CELULARES', 'celulares_subtraidos'),
    ('RECUPERADOS', 'veiculos_recuperados'),
    ('VEICULOS', 'veiculos'),
    ('PRESOS_E_APREENDIDOS', 'presos_apreendidos'),
    ('PRISOES', 'prisoes'),
    ('ARMAS_DE_FOGO', 'armas_apreendidas'),
    ('FLAGRANTES', 'flagrantes'),
    ('ART_173_ECA', 'apreensao_eca'),
    ('MDIP', 'mdip'),
    ('SPDADOSCRIMINAIS', 'criminal'),
    ('OBJETOS', 'objetos'),
]


def municipio_do_fato(row):
    """Município onde ocorreu o fato: código IBGE quando existe, senão o da circunscrição.
    NOME_MUNICIPIO é onde o BO foi registrado, que pode ser outra cidade."""
    ibge = (first(row, 'CD_IBGE', 'COD IBGE', 'COD_IBGE') or '').split('.')[0]
    if ibge == '3550308':
        return 'São Paulo'
    return clean_municipio(first(row, 'NOME_MUNICIPIO_CIRC', 'NOME_MUNICIPIO_CIRCUNSCRICAO',
                                 'NOME_MUNICIPIO_CIRCUNCRIÇÃO', 'MUNICIPIO_CIRCUNSCRICAO',
                                 'NOME_MUNICIPIO', 'CIDADE'))


def category(filename):
    normalized = re.sub(r'[^A-Z0-9]+', '_', filename.upper())
    for fragment, name in CATEGORIAS:
        if fragment in normalized:
            return name
    return 'outros'


def make_record(path, line_number, row):
    kind = category(path.name)
    date = parsed_date(first(row, 'DATA_OCORRENCIA_BO', 'DATA_FATO'))
    year = first(row, 'ANO_BO')
    try:
        year = int(year) if year else (date.year if date else None)
        if year is not None and not 1 <= year <= 9999:
            year = None
    except ValueError:
        year = date.year if date else None

    grams = parsed_decimal(first(row, 'QTDE (GRAMAS)', 'QTDE (GRAMAS) ARRED'))
    object_count = parsed_decimal(first(row, 'CONT_OBJETO'))
    drug_count = parsed_decimal(first(row, 'CONT_ENTORPECENTE'))
    if grams is not None:
        quantity, unit = grams, 'gramas'
    elif object_count is not None:
        quantity, unit = object_count, 'objetos'
    elif drug_count is not None:
        quantity, unit = drug_count, 'itens'
    else:
        quantity, unit = None, None

    lat, lon = valid_point(parsed_coord(first(row, 'LATITUDE'), -90, 90),
                           parsed_coord(first(row, 'LONGITUDE'), -180, 180))
    return (
        path.name, line_number, kind,
        municipio_do_fato(row),
        year, date, parsed_time(first(row, 'HORA_OCORRENCIA', 'HORA_OCORRENCIA_BO', 'HORA_FATO')),
        clean_cep(first(row, 'CEP')),
        first(row, 'BAIRRO'), hidden_address(first(row, 'LOGRADOURO', 'LOGRADOURO_VERSAO')),
        first(row, 'NUMERO_LOGRADOURO'), lat, lon,
        first(row, 'NATUREZA_APURADA', 'DESC_LEI'), first(row, 'RUBRICA'),
        first(row, 'DESCR_TIPO_OBJETO', 'DESCR_TIPO_VEICULO'),
        first(row, 'DESCR_SUBTIPO_OBJETO'), first(row, 'MARCA_OBJETO'),
        first(row, 'DESCR_TIPOLOCAL', 'DESC_TIPOLOCAL'), first(row, 'DESCR_MODO_OBJETO'),
        first(row, 'DESCR_TOXICO'), quantity, unit,
        first(row, 'NUM_BO'), first(row, 'ID_DELEGACIA'), first(row, 'CD_IBGE', 'COD IBGE', 'COD_IBGE'),
        Jsonb({k: v for k, v in row.items() if k and k not in CAMPOS_PESSOAIS})
    )


# Arquivos gerados por scripts/baixar_ssp.py: <Fonte>_<ano>[__<aba>].csv
ARQUIVO_DO_PIPELINE = re.compile(r'^(SPDadosCriminais|CelularesSubtraidos|VeiculosSubtraidos|ObjetosSubtraidos|'
                                 r'DadosProdutividade|MDIP)_\d{4}(__.*)?\.csv$')


def assinatura(path):
    """Hash do conteúdo: um CSV reconvertido com o mesmo conteúdo não é recarregado
    (recarregar custa caro: DELETE de centenas de milhares de linhas + COPY)."""
    with path.open('rb') as f:
        return 'sha1:' + hashlib.file_digest(f, 'sha1').hexdigest()


def assinatura_antiga(path):  # formato usado antes do hash; aceito para não recarregar tudo uma vez
    st = path.stat()
    return f'{st.st_size}:{st.st_mtime_ns}'


def carregar_arquivo(path, dsn, fila=None, refazer=False):
    """Carrega um CSV em uma transação própria (DELETE + COPY + carga_etl). Roda em processo filho.
    Retorna (registros, pulado)."""
    path = Path(path)
    progresso = ProgressoRemoto(fila) if fila is not None else None
    sig = assinatura(path)
    with psycopg.connect(dsn) as conn:
        if not refazer:
            ultima = conn.execute('SELECT assinatura, registros_importados FROM public.carga_etl '
                                  'WHERE arquivo = %s ORDER BY executada_em DESC LIMIT 1', (path.name,)).fetchone()
            if ultima and ultima[0] in (sig, assinatura_antiga(path)):
                return ultima[1], True
        chave = f'load:{path.name}'
        tamanho = path.stat().st_size
        if progresso:
            progresso.inicio(chave, f'carregando {path.stem}', total=tamanho)
        count = 0
        with conn.transaction():
            conn.execute('DELETE FROM public.registro_ocorrencia WHERE arquivo_origem = %s', (path.name,))
            with path.open('r', encoding='utf-8-sig', newline='') as source:
                reader = csv.DictReader(source, delimiter=';')
                if not reader.fieldnames:
                    raise ValueError(f'Arquivo sem cabeçalho: {path.name}')
                with conn.cursor().copy(COPY_SQL) as copy:
                    for line_number, row in enumerate(reader, start=2):
                        copy.write_row(make_record(path, line_number, row))
                        count += 1
                        if progresso and count % 20000 == 0:
                            progresso.avanco(chave, feito=source.buffer.tell())
            no_point = conn.execute(
                'SELECT count(*) FROM public.registro_ocorrencia WHERE arquivo_origem = %s AND localizacao IS NULL',
                (path.name,)).fetchone()[0]
            conn.execute(
                'INSERT INTO public.carga_etl (fonte, arquivo, categoria, registros_importados, '
                'registros_sem_coordenada, assinatura) VALUES (%s, %s, %s, %s, %s, %s)',
                ('ssp-sp', path.name, category(path.name), count, no_point, sig))
        if progresso:
            progresso.fim(chave, f'{path.name}: {count:,} registros')
    return count, False


def sincronizar(dsn, ativos, progresso):
    """Remove do banco os arquivos do pipeline que saíram do escopo (outras fontes/anos)."""
    with psycopg.connect(dsn) as conn:
        presentes = [r[0] for r in conn.execute('SELECT DISTINCT arquivo FROM public.carga_etl')]
        fora = [a for a in presentes if ARQUIVO_DO_PIPELINE.match(a) and a not in ativos]
        for arquivo in fora:
            with conn.transaction():
                n = conn.execute('DELETE FROM public.registro_ocorrencia WHERE arquivo_origem = %s',
                                 (arquivo,)).rowcount
                conn.execute('DELETE FROM public.carga_etl WHERE arquivo = %s', (arquivo,))
            progresso.log(f'  removido do banco (fora do escopo): {arquivo} ({n:,} registros)')


def carregar(files, dsn, progresso, workers=2, refazer=False):
    total, falhas = 0, []
    fila = progresso.fila() if hasattr(progresso, 'fila') else None
    with ProcessPoolExecutor(workers) as pool:
        tarefas = {pool.submit(carregar_arquivo, str(f), dsn, fila, refazer): f
                   for f in sorted(files, key=lambda f: -f.stat().st_size)}  # maiores primeiro
        for t in as_completed(tarefas):
            f = tarefas[t]
            try:
                count, pulado = t.result()
            except Exception as erro:
                progresso.log(f'✖ {f.name}: {erro}')
                falhas.append(f.name)
                continue
            total += count
            if pulado:
                progresso.log(f'  {f.name}: sem mudanças desde a última carga ({count:,} registros)')
    return total, falhas


def conexao(dsn):
    if dsn:
        return dsn
    password = os.getenv('PGPASSWORD') or getpass.getpass('Senha do PostgreSQL: ')
    return psycopg.conninfo.make_conninfo(
        host=os.getenv('PGHOST', 'localhost'), port=os.getenv('PGPORT', '5432'),
        dbname=os.getenv('PGDATABASE', 'pi2_seguranca_publica'), user=os.getenv('PGUSER', 'postgres'),
        password=password)


def main():
    parser = argparse.ArgumentParser(description='Carrega os CSVs SSP em PostgreSQL/PostGIS.')
    origem = parser.add_mutually_exclusive_group(required=True)
    origem.add_argument('--diretorio', help='Pasta contendo os arquivos CSV fonte (carrega todos).')
    origem.add_argument('--manifesto', help='manifesto.json de baixar_ssp.py: carrega só o escopo atual '
                                            'e remove do banco o que saiu dele.')
    parser.add_argument('--dsn', default=os.getenv('DATABASE_URL'), help='DSN PostgreSQL (opcional).')
    parser.add_argument('--workers', type=int, default=max(2, (os.cpu_count() or 2) - 1))
    parser.add_argument('--refazer', action='store_true', help='recarrega mesmo arquivos sem mudanças')
    args = parser.parse_args()
    with Progresso() as progresso:
        total, falhas = executar(args, progresso)
    if falhas:
        raise SystemExit(f'Falharam: {", ".join(falhas)}')


def executar(args, progresso):
    dsn = conexao(args.dsn)
    if args.manifesto:
        manifesto = Path(args.manifesto)
        pasta = manifesto.parent / 'csv'
        nomes = [c for v in json.loads(manifesto.read_text()).values() for c in v['csvs']]
        files = [pasta / n for n in nomes if (pasta / n).is_file()]
        for n in sorted(set(nomes) - {f.name for f in files}):
            progresso.log(f'⚠ {n}: listado no manifesto mas ausente em {pasta}; rode a etapa ssp-baixar')
        sincronizar(dsn, set(nomes), progresso)
    else:
        files = sorted(p for p in Path(args.diretorio).glob('*.csv') if p.is_file())
    if not files:
        raise SystemExit('Nenhum CSV para carregar.')
    total, falhas = carregar(files, dsn, progresso, args.workers, args.refazer)
    progresso.log(f'Total: {total:,} registros em {len(files) - len(falhas)} arquivos.')
    return total, falhas


if __name__ == '__main__':
    main()
