import argparse
import csv
import getpass
import json
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

COLUMNS = [
    'arquivo_origem','linha_origem','categoria_dado','municipio','ano_bo',
    'data_ocorrencia','hora_ocorrencia','cep','bairro','logradouro','numero_logradouro',
    'latitude','longitude','natureza','rubrica','tipo_objeto','subtipo_objeto',
    'marca_objeto','tipo_local','modo_objeto','tipo_entorpecente','quantidade',
    'unidade_quantidade','dados_originais'
]
COPY_SQL = 'COPY public.registro_ocorrencia (' + ','.join(COLUMNS) + ') FROM STDIN'


def first(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and value.strip():
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


def clean_cep(value):
    if not value:
        return None
    digits = re.sub(r'\D', '', value)
    return digits if len(digits) == 8 and digits != '00000000' else None


def clean_municipio(value):
    if not value:
        return None
    normalized = re.sub(r'[^A-Z]', '', value.upper())
    if normalized == 'SAOPAULO':
        return 'São Paulo'
    return value


def category(filename):
    upper = filename.upper()
    if 'ENTORPECENTES_GRAMAS' in upper:
        return 'entorpecentes_gramas'
    if 'APREENSAO DE ENTORPECENTE' in upper:
        return 'apreensao_entorpecente'
    if 'CELULARESSUBTRAIDOS' in upper:
        return 'celulares_subtraidos'
    if 'VEICULOS' in upper:
        return 'veiculos'
    if 'PRISOES' in upper:
        return 'prisoes'
    if 'OBJETOS' in upper:
        return 'objetos'
    return 'outros'


def make_record(path, line_number, row):
    kind = category(path.name)
    date = parsed_date(first(row, 'DATA_OCORRENCIA_BO'))
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

    lat = parsed_coord(first(row, 'LATITUDE'), -90, 90)
    lon = parsed_coord(first(row, 'LONGITUDE'), -180, 180)
    return (
        path.name, line_number, kind,
        clean_municipio(first(row, 'NOME_MUNICIPIO', 'CIDADE', 'NOME_MUNICIPIO_CIRC')),
        year, date, parsed_time(first(row, 'HORA_OCORRENCIA', 'HORA_OCORRENCIA_BO')),
        clean_cep(first(row, 'CEP')),
        first(row, 'BAIRRO'), first(row, 'LOGRADOURO', 'LOGRADOURO_VERSAO'),
        first(row, 'NUMERO_LOGRADOURO'), lat, lon,
        first(row, 'NATUREZA_APURADA', 'DESC_LEI'), first(row, 'RUBRICA'),
        first(row, 'DESCR_TIPO_OBJETO', 'DESCR_TIPO_VEICULO'),
        first(row, 'DESCR_SUBTIPO_OBJETO'), first(row, 'MARCA_OBJETO'),
        first(row, 'DESCR_TIPOLOCAL'), first(row, 'DESCR_MODO_OBJETO'),
        first(row, 'DESCR_TOXICO'), quantity, unit, Jsonb(row)
    )


def main():
    parser = argparse.ArgumentParser(description='Carrega os CSVs SSP em PostgreSQL/PostGIS.')
    parser.add_argument('--diretorio', required=True, help='Pasta contendo os arquivos CSV fonte.')
    parser.add_argument('--dsn', default=os.getenv('DATABASE_URL'), help='DSN PostgreSQL (opcional).')
    args = parser.parse_args()
    directory = Path(args.diretorio)
    files = sorted(p for p in directory.glob('*.csv') if p.is_file())
    if not files:
        raise SystemExit(f'Nenhum CSV encontrado em: {directory}')

    conn_args = args.dsn or {
        'host': os.getenv('PGHOST', 'localhost'),
        'port': os.getenv('PGPORT', '5432'),
        'dbname': os.getenv('PGDATABASE', 'pi2_seguranca_publica'),
        'user': os.getenv('PGUSER', 'postgres'),
        'password': os.getenv('PGPASSWORD') or getpass.getpass('Senha do PostgreSQL: '),
    }
    total = 0
    with psycopg.connect(conn_args) as conn:
        for path in files:
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
            total += count
            print(f'{path.name}: {count:,} registros carregados')
    print(f'Total: {total:,} registros em {len(files)} arquivos.')


if __name__ == '__main__':
    main()
