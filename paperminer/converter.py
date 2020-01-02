import logging
import re
import sys

import six
from pdfminer import utils
from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.layout import LAParams, LTAnno, LTContainer
from pdfminer.pdffont import PDFUnicodeNotDefined
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.utils import apply_matrix_pt

from paperminer.layout import LTPageExtended, LTCharExtended, LTTextLineHorizontalExtended

log = logging.getLogger(__name__)
intro_header_pattern = re.compile('[\\d.]* ?introduction( .+)?', re.IGNORECASE)
ref_header_pattern = re.compile('[\\d.]* ?reference( .+)?', re.IGNORECASE)
abstract_header_pattern = re.compile('[\\d.]* ?abstract( .+)?', re.IGNORECASE)
background_header_pattern = re.compile('[\\d.]* ?background( .+)?', re.IGNORECASE)
figure_pattern = re.compile('figure( \\w\\d*)?: ?.*', re.IGNORECASE)
table_pattern = re.compile('table( \\w\\d*)?: ?.*', re.IGNORECASE)


class BasePaperAnalyzer(PDFLayoutAnalyzer):

    def __init__(self, rsrcmgr, pageno=1, laparams=None):
        super().__init__(rsrcmgr, pageno, laparams)
        self._stack = []
        self.cur_item = None
        return

    def begin_page(self, page, ctm):
        (x0, y0, x1, y1) = page.mediabox
        (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
        (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
        mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
        self.cur_item = LTPageExtended(self.pageno, mediabox)
        return

    def end_page(self, page):
        assert not self._stack, str(len(self._stack))
        assert isinstance(self.cur_item, LTPageExtended), str(type(self.cur_item))
        if self.laparams is not None:
            self.cur_item.analyze(self.laparams)
        self.pageno += 1
        self.receive_layout(self.cur_item)
        return

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        try:
            text = font.to_unichr(cid)
            assert isinstance(text, six.text_type), str(type(text))
        except PDFUnicodeNotDefined:
            text = self.handle_undefined_char(font, cid)
        textwidth = font.char_width(cid)
        textdisp = font.char_disp(cid)
        item = LTCharExtended(matrix, font, fontsize, scaling, rise, text, textwidth, textdisp, ncs, graphicstate)
        self.cur_item.add(item)
        return item.adv

    def handle_undefined_char(self, font, cid):
        log.info('undefined: %r, %r', font, cid)
        return '(cid:%d)' % cid

    def receive_layout(self, ltpage):
        return


class ExtendedPaperAnalyzer(BasePaperAnalyzer):
    def __init__(self, rsrcmgr, pageno=1):
        laparams = LAParams()
        for param in ("all_texts", "detect_vertical", "word_margin", "char_margin", "line_margin", "boxes_flow"):
            paramv = locals().get(param, None)
            if paramv is not None:
                setattr(laparams, param, paramv)
        BasePaperAnalyzer.__init__(self, rsrcmgr, pageno=pageno, laparams=laparams)
        return

    # a typical page is 612 x 792 in pts or 8.5 x 11 in inches
    # some common margin conversions: 1in = 72 pts, 0.5in = 36 pts
    # LaTeX margins are probably going to be between 36-72pts
    # anything drawn in the first 0.25 - 0.5 of the page is possibly a title + authors
    # So that is 0 - [198-396] pts
    def receive_layout(self, ltpage):
        def render(item, parent, level, rsrcmgr):
            # if not isinstance(item, LTCharExtended) and not isinstance(item, LTAnno):
            #    print(f'{"".join([" "] * level)} -> {item.__class__.__name__} {item.y1 if isinstance(item, LTTextLineHorizontalExtended) else ""}')
            if isinstance(item, LTTextLineHorizontalExtended):
                if rsrcmgr.top_margin_ref is None:
                    rsrcmgr.top_margin_ref = item
                if item.left_margin < rsrcmgr.left_margin:
                    rsrcmgr.left_margin = item.left_margin
                if item.right_margin > rsrcmgr.right_margin:
                    rsrcmgr.right_margin = item.right_margin
                if intro_header_pattern.match(item.get_text()) is not None:
                    rsrcmgr.intro_ref.append(item)
                if background_header_pattern.match(item.get_text()) is not None:
                    rsrcmgr.background_ref.append(item)
                if abstract_header_pattern.match(item.get_text()) is not None and\
                        'extended' not in item.get_text().lower():
                    rsrcmgr.abstract_ref.append(item)
                if ref_header_pattern.match(item.get_text()) is not None:
                    rsrcmgr.ref_ref.append(item)
                if figure_pattern.match(item.get_text()) is not None:
                    rsrcmgr.figure_ref.append(item)
                if table_pattern.match(item.get_text()) is not None:
                    rsrcmgr.table_ref.append(item)
            elif isinstance(item, LTContainer):
                for child in item:
                    render(child, item, level + 1, rsrcmgr)

        render(ltpage, None, 0, self.rsrcmgr)
        return


class PaperToTextConverter(ExtendedPaperAnalyzer):
    def __init__(self, document):
        super().__init__(PaperResourceManager())
        self.document = document
        analyzer = ExtendedPaperAnalyzer(self.rsrcmgr)
        interpreter = PDFPageInterpreter(self.rsrcmgr, analyzer)
        for page in PDFPage.create_pages(document):
            interpreter.process_page(page)
        return

    @staticmethod
    def write_text(text):
        text = utils.compatible_encode_method(text, 'utf-8', 'ignore')
        sys.stdout.write(text)
        return

    def receive_layout(self, ltpage):
        def render(item):
            if isinstance(item, LTTextLineHorizontalExtended):
                for child in item:
                    self.write_text(child.get_text())
            elif isinstance(item, LTContainer):
                for child in item:
                    render(child)

        render(ltpage)
        return

    def get_result(self):
        interpreter = PDFPageInterpreter(self.rsrcmgr, self)
        for page in PDFPage.create_pages(self.document):
            interpreter.process_page(page)
        return


class PaperResourceManager(PDFResourceManager):
    def __init__(self):
        super().__init__()
        self.intro_ref = []
        self.background_ref = []
        self.text_ref = []
        self.figure_ref = []
        self.abstract_ref = []
        self.table_ref = []
        self.after_ref = False
        self.ref_ref = []
        self.top_margin_ref = None
        self.left_margin = 612
        self.right_margin = 0
        self.smallest_ref = []
