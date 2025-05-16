from flask import Flask, render_template, request, send_file
from io import BytesIO
import exifread
import pandas as pd
import re
import os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

def safe_get(dictionary, key, default=pd.NA):
    return str(dictionary.get(key, default)) if dictionary else str(default)

def processar_exif(arquivo):
    try:
        return exifread.process_file(arquivo)
    except Exception as e:
        print(f"Erro ao processar EXIF: {str(e)}")
        return {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/processar', methods=['POST'])
def processar():
    try:
        if 'fotos' not in request.files:
            return "Erro: Nenhum arquivo enviado", 400
            
        arquivos = request.files.getlist('fotos')
        if not arquivos or arquivos[0].filename == '':
            return "Erro: Nenhum arquivo selecionado", 400

        # Processamento das tags EXIF
        colunas_essenciais = [
            "Image ImageDescription",
            "Image DateTime",
            "GPS GPSLatitude",
            "GPS GPSLongitude"
        ]

        dados = []
        for arquivo in arquivos:
            tags = processar_exif(arquivo)
            linha = {col: safe_get(tags, col) for col in colunas_essenciais}
            dados.append(linha)

        # Criação do DataFrame
        df = pd.DataFrame(dados).rename(columns={
            'Image ImageDescription': 'Individuo',
            'Image DateTime': 'DataHora',
            'GPS GPSLatitude': 'Latitude',
            'GPS GPSLongitude': 'Longitude'
        })

        # Processamento de data/hora
        df[['Data', 'Hora']] = df['DataHora'].str.split(' ', 1, expand=True)
        df['Data'] = pd.to_datetime(df['Data'].str.replace(':', '-', 2), errors='coerce').dt.strftime('%d-%m-%Y')
        df['Hora'] = df['Hora'].str.strip()

        # Processamento de coordenadas
        for coord in ['Latitude', 'Longitude']:
            df[coord] = df[coord].apply(
                lambda x: [str(v) for v in x.values] if x and hasattr(x, 'values') else [pd.NA]*3
            )
            df[f'{coord}_GMS'] = df[coord].apply(
                lambda x: f"{x[0]}°{x[1]}'{float(x[2]):.2f}\"" if pd.notna(x[0]) else pd.NA
            )

        df['Coordenadas'] = df['Latitude_GMS'] + '; ' + df['Longitude_GMS']
        
        # Ordenação e seleção final
        df_final = df.assign(
            Individuo=df['Individuo'].str.extract('(\d+)')[0].fillna(0).astype(int)
        ).sort_values('Individuo')[
            ['Individuo', 'Coordenadas', 'Data', 'Hora']
        ]

        # Geração do Excel
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
        return f"ERRO INTERNO: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=False)
