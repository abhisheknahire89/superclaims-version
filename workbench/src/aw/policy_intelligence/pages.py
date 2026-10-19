"""Long policy wordings: native reading, bounded local OCR only for pages needing it."""
import io
from ..extraction.pages import PageText,MIN_NATIVE_CHARS,render_png,_r

def read_pdf(data):
 import pdfplumber
 pages=[];ocr_pixels=0
 with pdfplumber.open(io.BytesIO(data)) as pdf:
  if not 0<len(pdf.pages)<=100:raise ValueError('PDF_PAGE_LIMIT')
  for n,page in enumerate(pdf.pages,1):
   pixels=page.width*page.height*(220/72)**2
   if pixels>40_000_000:raise ValueError('PDF_RASTER_LIMIT')
   lines=[{k:ln[k] if k=='text' else _r(ln[k]) for k in ('text','x0','top','x1','bottom')} for ln in page.extract_text_lines(return_chars=False)]
   text='\n'.join(ln['text'] for ln in lines)
   if len(text.replace(' ',''))<MIN_NATIVE_CHARS:
    ocr_pixels+=pixels
    if ocr_pixels>200_000_000:raise ValueError('PDF_TOTAL_OCR_LIMIT')
    from ..extraction.ocr import read_image
    pages.append(read_image(render_png(data,n,220),n,_r(page.width),_r(page.height)))
   else:pages.append(PageText(n,_r(page.width),_r(page.height),text,lines,[], 'NATIVE'))
 return pages
