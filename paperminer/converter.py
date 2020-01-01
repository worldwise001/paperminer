import logging
import sys

import six
from pdfminer import utils
from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.layout import LAParams, LTAnno, LTTextLineHorizontal, LTContainer
from pdfminer.pdffont import PDFUnicodeNotDefined
from pdfminer.utils import apply_matrix_pt

from paperminer.layout import LTPageExtended, LTCharExtended, LTTextLineHorizontalExtended

log = logging.getLogger(__name__)


class PaperLayoutAnalyzer(PDFLayoutAnalyzer):

    def __init__(self, rsrcmgr, pageno=1, laparams=None):
        super().__init__(rsrcmgr, pageno, laparams)
        self._stack = []
        self.cur_item = None
        self.printed = 0
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
        if self.printed == 0:
            # traceback.print_stack()
            self.printed = 1
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


class PaperToTextConverter(PaperLayoutAnalyzer):
    def __init__(self, rsrcmgr, pageno=1):
        laparams = LAParams()
        for param in ("all_texts", "detect_vertical", "word_margin", "char_margin", "line_margin", "boxes_flow"):
            paramv = locals().get(param, None)
            if paramv is not None:
                setattr(laparams, param, paramv)
        PaperLayoutAnalyzer.__init__(self, rsrcmgr, pageno=pageno, laparams=laparams)
        return

    @staticmethod
    def write_text(text):
        text = utils.compatible_encode_method(text, 'utf-8', 'ignore')
        text = text.encode()
        sys.stdout.write(text)
        return

    # a typical page is 612 x 792 in pts or 8.5 x 11 in inches
    # some common margin conversions: 1in = 72 pts, 0.5in = 36 pts
    # LaTeX margins are probably going to be between 36-72pts
    # anything drawn in the first 0.25 - 0.5 of the page is possibly a title + authors
    # So that is 0 - [198-396] pts
    def receive_layout(self, ltpage):
        def render(item, parent, level):
            if not isinstance(item, LTCharExtended) and not isinstance(item, LTAnno):
                print(
                    f'{"".join([" "] * level)} -> {item.__class__.__name__} {item.y1 if isinstance(item, LTPageExtended) else ""}')
            if isinstance(item, LTTextLineHorizontalExtended):
                print(f'{"".join([" "] * level)}      {item.fontsize} {item.get_text()}')
                for child in item:
                    self.write_text(child.get_text())
            elif isinstance(item, LTContainer):
                for child in item:
                    render(child, item, level + 1)

        render(ltpage, None, 0)
        return
