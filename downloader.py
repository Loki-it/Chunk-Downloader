import asyncio
import aiohttp
import os
from urllib.parse import urlparse

CHUNK_SIZE = 2048 * 2048  # Dimensione dei chunk (4 MB), se non bypassa prova a mettere 1024 * 1024  
NUM_CHUNKS = 100  # Numero di chunk da scaricare simultaneamente
async def download_chunk(session, url, start_byte, end_byte, chunk_index):
    headers = {'Range': f'bytes={start_byte}-{end_byte}'}
    async with session.get(url, headers=headers) as response:
        chunk = await response.read()
        
        chunk_dir = 'chunk_directory'
        if not os.path.exists(chunk_dir):
            os.makedirs(chunk_dir)
        
        chunk_filename = os.path.join(chunk_dir, f'chunk_{chunk_index}')
        with open(chunk_filename, 'wb') as f:
            f.write(chunk)
        
        print(f"Chunk {chunk_index} scaricato")

async def main():
    url = input("Inserisci il link: ")
    async with aiohttp.ClientSession() as session:
        async with session.head(url) as response:
            file_size = int(response.headers['Content-Length'])
            content_type = response.headers.get('content-type')
            parsed_url = urlparse(url)
            file_extension = os.path.splitext(parsed_url.path)[1]
        
        num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        tasks = []
        for chunk_index in range(num_chunks):
            start_byte = chunk_index * CHUNK_SIZE
            end_byte = min((chunk_index + 1) * CHUNK_SIZE - 1, file_size - 1)
            task = download_chunk(session, url, start_byte, end_byte, chunk_index)
            tasks.append(task)
            if len(tasks) >= NUM_CHUNKS:
                await asyncio.gather(*tasks)
                tasks = []

        if tasks:
            await asyncio.gather(*tasks)

        print("Tutti i chunk sono stati scaricati.")

        downloaded_filename = f'file_scaricato{file_extension}'
        with open(downloaded_filename, 'wb') as output_file:
            for chunk_index in range(num_chunks):
                chunk_filename = os.path.join('chunk_directory', f'chunk_{chunk_index}')
                with open(chunk_filename, 'rb') as chunk_file:
                    output_file.write(chunk_file.read())
                os.remove(chunk_filename)
        os.rmdir('chunk_directory')

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Si è verificato un errore: {e}")
