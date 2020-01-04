import logging
import re
import sys
from typing import Optional, Tuple, Dict, List, Any

import six
from pdfminer import utils
from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.layout import LAParams, LTAnno, LTContainer, LTPage, LTItem, LTTextBox
from pdfminer.pdfcolor import PDFColorSpace
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdffont import PDFUnicodeNotDefined, PDFFont
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager, PDFGraphicState
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


class PaperResourceManager(PDFResourceManager):
    def __init__(self) -> None:
        super().__init__()
        self.section_header_ref: List[LTTextBox] = []
        self.text_ref: List[LTTextBox] = []
        self.figure_ref: List[LTTextBox] = []
        self.abstract_ref: Optional[LTTextBox] = None
        self.table_ref: List[LTTextBox] = []
        self.ref_ref: Optional[LTTextBox] = None
        self.top_margin_ref: Optional[LTTextBox] = None
        self.left_margin: float = 612
        self.right_margin: float = 0
        self.after_title = False
        self.after_abstract = False
        self.after_ref = False
        self.section_header_font: Optional[PDFFont] = None
        self.section_header_font_size = 0

    def post_process(self) -> None:
        # figure out section header fonts
        font_freq: Dict[Tuple[PDFFont, float], int] = {}
        key = None
        for item in self.section_header_ref:
            key = (item.font, item.fontsize)
            if key not in font_freq:
                font_freq[key] = 0
            font_freq[key] += 1
        if key:
            max_key = key
            for k in font_freq.keys():
                if font_freq[k] > font_freq[max_key]:
                    max_key = k
            self.section_header_font, self.section_header_font_size = max_key


class BasePaperAnalyzer(PDFLayoutAnalyzer):

    def __init__(self, rsrcmgr: PaperResourceManager, pageno: int = 1, laparams: Optional[LAParams] = None) -> None:
        super().__init__(rsrcmgr, pageno, laparams)
        self.cur_item: Any = None
        return

    def begin_page(self, page: PDFPage, ctm: Tuple[int, int, int, int, int, int]) -> None:
        (x0, y0, x1, y1) = page.mediabox
        (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
        (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
        mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
        self.cur_item = LTPageExtended(self.pageno, mediabox)
        return

    def end_page(self, page: PDFPage) -> None:
        assert not self._stack, str(len(self._stack))
        assert isinstance(self.cur_item, LTPageExtended), str(type(self.cur_item))
        if self.laparams is not None:
            self.cur_item.analyze(self.laparams)
        self.pageno += 1
        self.receive_layout(self.cur_item)
        return

    def render_char(self,
                    matrix: Tuple[int, int, int, int, int, int],
                    font: PDFFont,
                    fontsize: float,
                    scaling: float,
                    rise: float,
                    cid: bytearray,
                    ncs: PDFColorSpace,
                    graphicstate: PDFGraphicState) -> None:
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

    def receive_layout(self, ltpage: LTPage) -> None:
        return


class ExtendedPaperAnalyzer(BasePaperAnalyzer):
    def __init__(self, rsrcmgr: PaperResourceManager, pageno: int = 1) -> None:
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
    def receive_layout(self, ltpage: LTPageExtended) -> None:
        def render(item: LTItem, parent: Optional[LTItem], level: int, rsrcmgr: PaperResourceManager) -> None:
            if isinstance(item, LTTextLineHorizontalExtended):
                if not rsrcmgr.top_margin_ref:
                    rsrcmgr.top_margin_ref = item
                if item.left_margin < rsrcmgr.left_margin:
                    rsrcmgr.left_margin = item.left_margin
                if item.right_margin > rsrcmgr.right_margin:
                    rsrcmgr.right_margin = item.right_margin
                if intro_header_pattern.match(item.get_text()):
                    rsrcmgr.section_header_ref.append(item)
                if background_header_pattern.match(item.get_text()):
                    rsrcmgr.section_header_ref.append(item)
                if not rsrcmgr.abstract_ref and abstract_header_pattern.match(item.get_text()) and\
                        'extended' not in item.get_text().lower():
                    rsrcmgr.abstract_ref = item
                    rsrcmgr.section_header_ref.append(item)
                if ref_header_pattern.match(item.get_text()):
                    rsrcmgr.ref_ref = item
                    rsrcmgr.section_header_ref.append(item)
                if figure_pattern.match(item.get_text()):
                    rsrcmgr.figure_ref.append(item)
                if table_pattern.match(item.get_text()):
                    rsrcmgr.table_ref.append(item)
            elif isinstance(item, LTContainer):
                for child in item:
                    render(child, item, level + 1, rsrcmgr)

        render(ltpage, None, 0, self.rsrcmgr)
        return


class PaperToTextConverter(ExtendedPaperAnalyzer):
    def __init__(self, document: PDFDocument) -> None:
        super().__init__(PaperResourceManager())
        self.document = document
        analyzer = ExtendedPaperAnalyzer(self.rsrcmgr)
        interpreter = PDFPageInterpreter(self.rsrcmgr, analyzer)
        for page in PDFPage.create_pages(document):
            interpreter.process_page(page)
        self.rsrcmgr.post_process()
        return

    def begin_page(self, page: int, ctm: Tuple[int, int, int, int, int, int]) -> None:
        super().begin_page(page, ctm)
        self.cur_item.rsrcmgr = self.rsrcmgr
        return

    @staticmethod
    def write_text(text: str) -> None:
        text = utils.compatible_encode_method(text, 'utf-8', 'ignore')
        sys.stdout.write(text)
        return

    def receive_layout(self, ltpage: LTPage) -> None:
        def render(item: LTItem, parent: Optional[LTItem], level: int) -> None:
            if not isinstance(item, LTCharExtended) and not isinstance(item, LTAnno):
                if parent.__class__.__name__ == 'LTTextBoxHorizontal' or isinstance(parent, LTPageExtended):
                    print(f'{"".join([" "] * level)} -> {item.__class__.__name__} '
                          f'{item.y1 if isinstance(item, LTTextLineHorizontalExtended) else ""}')
            if isinstance(item, LTTextLineHorizontalExtended):
                for child in item:
                    self.write_text(child.get_text())
            elif isinstance(item, LTContainer):
                for child in item:
                    render(child, item, level + 1)

        render(ltpage, None, 0)
        return

    def get_result(self) -> None:
        interpreter = PDFPageInterpreter(self.rsrcmgr, self)
        for page in PDFPage.create_pages(self.document):
            interpreter.process_page(page)
        return
