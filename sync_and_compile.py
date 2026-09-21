import os
import json
import subprocess
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

TEX_FOLDER_ID = os.environ['DRIVE_TEX_FOLDER_ID']
PDF_FOLDER_ID = os.environ['DRIVE_PDF_FOLDER_ID']
SA_KEY_JSON = os.environ['GCP_SA_KEY']

# Drive API 認証
creds_dict = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(
    creds_dict,
    scopes=['https://www.googleapis.com/auth/drive']
)
service = build('drive', 'v3', credentials=creds)

# 1. texフォルダ内のファイル一覧を取得
results = service.files().list(
    q=f"'{TEX_FOLDER_ID}' in parents and trashed = false and (mimeType = 'text/x-tex' or name contains '.tex')",
    fields="files(id, name)"
).execute()
tex_files = results.get('files', [])

# 2. 既にpdfフォルダに存在するファイル名を取得（二重コンパイル防止）
pdf_results = service.files().list(
    q=f"'{PDF_FOLDER_ID}' in parents and trashed = false",
    fields="files(name)"
).execute()
existing_pdfs = {f['name'] for f in pdf_results.get('files', [])}

for item in tex_files:
    tex_name = item['name']
    base_name = os.path.splitext(tex_name)[0]
    pdf_name = f"{base_name}.pdf"

    if pdf_name in existing_pdfs:
        print(f"Skipping {tex_name} (already compiled)")
        continue

    print(f"Processing: {tex_name}")
    # ダウンロード
    request = service.files().get_media(fileId=item['id'])
    with open(tex_name, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    # LuaLaTeX でコンパイル (2回コンパイルして目次・参照を確定)
    subprocess.run(['latexmk', '-lualatex', '-interaction=nonstopmode', tex_name], check=True)

    # PDF をDriveにアップロード
    if os.path.exists(pdf_name):
        file_metadata = {
            'name': pdf_name,
            'parents': [PDF_FOLDER_ID]
        }
        media = MediaFileUpload(pdf_name, mimetype='application/pdf')
        service.files().create(body=file_metadata, media_body=media).execute()
        print(f"Uploaded: {pdf_name}")