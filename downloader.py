import asyncio
import aiohttp
import os
from urllib.parse import urlparse
from pathlib import Path
import time
import logging
from typing import Optional, Tuple
import mimetypes

# Configuration
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB
MAX_CONCURRENT_CHUNKS = 100  # Maximum number of concurrent chunks
CHUNK_DIR = Path('chunk_temp')  # Directory for temporary chunks
RETRY_ATTEMPTS = 3  # Retry attempts for each chunk
TIMEOUT = aiohttp.ClientTimeout(total=60)  # Timeout for HTTP requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

async def download_chunk_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    start_byte: int,
    end_byte: int,
    chunk_index: int
) -> bool:
    """Downloads a chunk with a retry mechanism."""
    headers = {'Range': f'bytes={start_byte}-{end_byte}'}
    
    for attempt in range(RETRY_ATTEMPTS):
        try:
            async with session.get(url, headers=headers, timeout=TIMEOUT) as response:
                response.raise_for_status()
                chunk_data = await response.read()
                
                chunk_file = CHUNK_DIR / f'chunk_{chunk_index:04d}'
                with open(chunk_file, 'wb') as f:
                    f.write(chunk_data)
                
                logger.debug(f"Chunk {chunk_index} downloaded (attempt {attempt + 1})")
                return True
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Attempt {attempt + 1} failed for chunk {chunk_index}: {str(e)}")
            if attempt == RETRY_ATTEMPTS - 1:
                logger.error(f"Failed after {RETRY_ATTEMPTS} attempts for chunk {chunk_index}")
                return False
            await asyncio.sleep(1 * (attempt + 1)) 

    return False

def determine_file_extension(url: str, content_type: str) -> str:
    """Determines the file extension based on URL and content-type."""
    parsed_url = urlparse(url)
    file_extension = os.path.splitext(parsed_url.path)[1].lower()
    
    if not file_extension:
        if content_type:
            main_type = content_type.split(';')[0].split('/')[-1]
            
            extension_map = {
                'jpeg': '.jpg',
                'png': '.png',
                'mpeg': '.mp3',
                'mp4': '.mp4',
                'pdf': '.pdf',
                'zip': '.zip',
                'vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
                'vnd.ms-excel': '.xls',
                'msword': '.doc',
                'vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                'octet-stream': '.bin'
            }
            
            file_extension = extension_map.get(main_type, f'.{main_type}')
        else:
            file_extension = '.bin'
    
    if not file_extension.startswith('.'):
        file_extension = f'.{file_extension}'
    
    return file_extension

async def get_file_info(session: aiohttp.ClientSession, url: str) -> Tuple[int, str, str]:
    """Gets information about the file to download."""
    async with session.head(url) as response:
        response.raise_for_status()
        
        if 'Content-Length' not in response.headers:
            raise ValueError("The server does not provide file size information")
            
        file_size = int(response.headers['Content-Length'])
        content_type = response.headers.get('Content-Type', 'application/octet-stream')
        file_extension = determine_file_extension(url, content_type)
        
        return file_size, file_extension, content_type

async def download_file(url: str, output_path: Optional[str] = None) -> None:
    """Downloads a file efficiently using parallel chunks."""
    start_time = time.time()
    
    CHUNK_DIR.mkdir(exist_ok=True)
    
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        try:
            file_size, file_extension, content_type = await get_file_info(session, url)
            logger.info(f"Downloading file of {file_size / (1024 * 1024):.2f} MB ({content_type})")
            
            num_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
            logger.info(f"Using {num_chunks} chunks of {CHUNK_SIZE / (1024 * 1024):.2f} MB each")
            
            if not output_path:
                output_path = f'downloaded_file{file_extension}'
            
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)
            
            async def limited_download_chunk(chunk_index: int):
                async with semaphore:
                    start_byte = chunk_index * CHUNK_SIZE
                    end_byte = min((chunk_index + 1) * CHUNK_SIZE - 1, file_size - 1)
                    success = await download_chunk_with_retry(session, url, start_byte, end_byte, chunk_index)
                    if not success:
                        raise RuntimeError(f"Download failed for chunk {chunk_index}")
            
            tasks = [limited_download_chunk(i) for i in range(num_chunks)]
            await asyncio.gather(*tasks)
            
            logger.info("Combining chunks...")
            with open(output_path, 'wb') as output_file:
                for chunk_index in range(num_chunks):
                    chunk_file = CHUNK_DIR / f'chunk_{chunk_index:04d}'
                    with open(chunk_file, 'rb') as f:
                        output_file.write(f.read())
                    chunk_file.unlink()
            
            CHUNK_DIR.rmdir()
            
            download_time = time.time() - start_time
            speed = file_size / (1024 * 1024) / download_time if download_time > 0 else 0
            logger.info(
                f"Download completed in {download_time:.2f} seconds "
                f"({speed:.2f} MB/s). File saved to: {output_path}"
            )
            
        except Exception as e:
            logger.error(f"Error during download: {str(e)}")
            raise
        finally:
            for chunk_file in CHUNK_DIR.glob('chunk_*'):
                try:
                    chunk_file.unlink()
                except OSError:
                    pass

async def main():
    try:
        url = input("Enter the URL of the file to download: ").strip()
        output_path = input("Enter the output path (leave empty for default): ").strip() or None
        
        await download_file(url, output_path)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        if CHUNK_DIR.exists():
            for chunk_file in CHUNK_DIR.glob('chunk_*'):
                try:
                    chunk_file.unlink()
                except OSError:
                    pass
            try:
                CHUNK_DIR.rmdir()
            except OSError:
                pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Download interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}")
