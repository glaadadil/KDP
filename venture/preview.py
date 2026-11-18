"""Render a bounded PDF page to inert pixels. PDFium calls must be serialised."""
from io import BytesIO
from threading import Lock
import pypdfium2 as pdfium

_lock=Lock()
def pdf_page(path,number):
    with _lock:
        doc=pdfium.PdfDocument(str(path))
        try:
            page=doc[number-1]
            try:
                width,height=page.get_size()
                bitmap=page.render(scale=min(2.0,1400/max(width,height)))
                try:
                    buf=BytesIO()
                    bitmap.to_pil().save(buf,format="PNG")
                    return buf.getvalue()
                finally: bitmap.close()
            finally: page.close()
        finally: doc.close()
