"""Free local OCR. Original images remain unchanged; boxes map back to original pixels."""
from __future__ import annotations
import csv
import io
import subprocess
import tempfile
from pathlib import Path
from .pages import PageText


def read_image(data: bytes, page_no=1, width_pt=None, height_pt=None) -> PageText:
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as source:
        if source.width * source.height > 40_000_000:
            raise ValueError('IMAGE_PIXEL_LIMIT')
        image = ImageOps.exif_transpose(source).convert('RGB')
        gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    width, height = width_pt or w, height_pt or h
    # Hough line orientation is independent of document labels or hospital layout.
    edges = cv2.Canny(gray, 50, 150)
    segments = cv2.HoughLinesP(edges, 1, np.pi / 1800, threshold=80, minLineLength=w // 5, maxLineGap=20)
    angles = []
    if segments is not None:
        for x1,y1,x2,y2 in segments.reshape(-1,4):
            angle = np.degrees(np.arctan2(y2-y1, x2-x1))
            if abs(angle) < 12:
                angles.append(angle)
    angle = float(np.median(angles)) if angles else 0.0
    transform = cv2.getRotationMatrix2D((w/2,h/2), angle, 1)
    inverse = cv2.invertAffineTransform(transform)
    clean = cv2.warpAffine(gray, transform, (w,h), borderValue=255)
    clean = cv2.medianBlur(clean, 3)
    with tempfile.TemporaryDirectory(prefix='aw-ocr-') as td:
        path = Path(td)/'page.png'
        cv2.imwrite(str(path), clean)
        try:
            result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng', '--psm', '6', 'tsv'],
                                    capture_output=True, timeout=60, check=True)
        except FileNotFoundError as e:
            raise RuntimeError('LOCAL_TESSERACT_REQUIRED') from e
    words, grouped = [], {}
    for row in csv.DictReader(io.StringIO(result.stdout.decode()), delimiter='\t'):
        text = (row.get('text') or '').strip()
        if not text or float(row['conf']) < 0:
            continue
        x,y,bw,bh = (int(row[k]) for k in ('left','top','width','height'))
        points = np.array([[x,y,1],[x+bw,y,1],[x,y+bh,1],[x+bw,y+bh,1]]) @ inverse.T
        word = {'text': text, 'x0': round(max(0,float(points[:,0].min()))*width/w,1),
                'x1': round(min(w,float(points[:,0].max()))*width/w,1),
                'top': round(max(0,float(points[:,1].min()))*height/h,1),
                'bottom': round(min(h,float(points[:,1].max()))*height/h,1),
                'confidence': max(0,min(1,float(row['conf'])/100))}
        words.append(word)
        grouped.setdefault((row['block_num'],row['par_num'],row['line_num']), []).append(word)
    lines = [{'text':' '.join(v['text'] for v in ws), 'x0':min(v['x0'] for v in ws),
              'top':min(v['top'] for v in ws), 'x1':max(v['x1'] for v in ws),
              'bottom':max(v['bottom'] for v in ws), 'confidence':min(v['confidence'] for v in ws)}
             for ws in grouped.values()]
    text = '\n'.join(ln['text'] for ln in lines)
    return PageText(page_no, width, height, text, lines, words, 'OCR' if text.strip() else 'NONE')
