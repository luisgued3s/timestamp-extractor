from flask import Flask, render_template, request, send_file
from io import BytesIO
import exifread
import pandas as pd
import re
import os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

def fracao_para_float(fracao_str):
    try:
        if '/' in fracao_str:
            numerador, denominador = map(float, fracao_str.split('/'))
            return numerador / denominador
        return float(fracao_str)
    except:
        return 0.0

def parse_gps_string(gps_str):
    try:
        partes = [p.strip() for p in gps_str.split(',')]
        graus = abs(int(partes[0]))
        minutos = int(partes[1])
        segundos = fracao_para_float(partes[2])
        
        # Garantir valores válidos para minutos/segundos
        minutos = min(max(minutos, 0), 59)
        segundos = min(max(segundos, 0), 59.999)
        
        return graus, minutos, segundos
    except Exception as e:
        return (0, 0, 0)

def formatar_gms(graus, minutos, segundos, direcao):
    return f"{direcao}{graus}°{minutos}'{segundos:.5f}\""

def converter_coordenada_para_gms(coord_str, direcao_pos, direcao_neg):
    try:
        coord_str = coord_str.replace(' ', '')
        graus, minutos, segundos = parse_gps_string(coord_str)
        
        # Determinar direção com base no sinal original
        negativo = '-' in coord_str.split(',')[0]
        direcao = direcao_neg if negativo else direcao_pos
        
        return formatar_gms(graus, minutos, segundos, direcao)
    except Exception as e:
        return pd.NA

def processar_exif(arquivo):
    try:
        tags = exifread.process_file(arquivo)
        return {
            'Image ImageDescription': str(tags.get('Image ImageDescription', '')),
            'Image DateTime': str(tags.get('Image DateTime', '')),
            'GPS GPSLatitude': tags.get('GPS GPSLatitude'),
            'GPS GPSLongitude': tags.get('GPS GPSLongitude')
        }
    except Exception as e:
        print(f"Erro no EXIF: {str(e)}")
        return {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/processar', methods=['POST'])
def processar():
    try:
        if 'fotos' not in request.files:
            return "Nenhum arquivo enviado", 400
            
        arquivos = request.files.getlist('fotos')
        if not arquivos or arquivos[0].filename == '':
            return "Nenhum arquivo válido selecionado", 400

        dados = []
        for arquivo in arquivos:
            try:
                tags = processar_exif(arquivo)
                linha = {
                    'N° Indivíduo': tags['Image ImageDescription'].strip(),
                    'DataHora': tags['Image DateTime'],
                    'Latitude': tags['GPS GPSLatitude'],
                    'Longitude': tags['GPS GPSLongitude']
                }
                dados.append(linha)
            except Exception as e:
                print(f"Erro no arquivo {arquivo.filename}: {str(e)}")

        df = pd.DataFrame(dados)
        
        # Processamento de data/hora
        df[['Data', 'Hora']] = df['DataHora'].str.split(' ', 1, expand=True)
        df['Data'] = pd.to_datetime(
            df['Data'].str.replace(':', '-', 2), 
            errors='coerce'
        ).dt.strftime('%d-%m-%Y')
        df['Hora'] = df['Hora'].str.strip()
        
        # Processamento de coordenadas
        for coord, direcoes in [('Latitude', ('S', 'N')), ('Longitude', ('W', 'E'))]:
            df[coord] = df[coord].apply(
                lambda x: ', '.join([str(v) for v in x.values]) if x else pd.NA
            )
            df[f'{coord}_GMS'] = df[coord].apply(
                lambda x: converter_coordenada_para_gms(x, *direcoes) if pd.notna(x) else pd.NA
            )
        
        df['Coordenadas'] = df['Latitude_GMS'] + '; ' + df['Longitude_GMS']
        
        # Ordenação e formatação final
        df['N° Indivíduo'] = df['N° Indivíduo'].str.extract('(\d+)')[0].fillna(0).astype(int)
        df = df.sort_values('N° Indivíduo')
        
        df_final = df[[
            'N° Indivíduo',
            'Coordenadas',
            'Data',
            'Hora'
        ]]

        output = BytesIO()
        df_final.to_excel(output, index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            download_name="dados_geograficos.xlsx",
            as_attachment=True
        )

    except Exception as e:
        return f"Erro interno: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=False)
