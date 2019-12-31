
##  PDFLayoutAnalyzer
##
import logging
import sys
import traceback

import six
from pdfminer import utils
from pdfminer.layout import LTPage, LTFigure, LTImage, LTLine, LTRect, LTCurve, LTChar, LTTextLineHorizontal, \
    LTContainer, LTAnno, LAParams
from pdfminer.pdfdevice import PDFTextDevice
from pdfminer.pdffont import PDFUnicodeNotDefined
from pdfminer.utils import apply_matrix_pt, mult_matrix

log = logging.getLogger(__name__)

class PDFLayoutAnalyzer(PDFTextDevice):

    def __init__(self, rsrcmgr, pageno=1, laparams=None):
        PDFTextDevice.__init__(self, rsrcmgr)
        self.pageno = pageno
        self.laparams = laparams
        self._stack = []
        self.cur_item = None
        self.printed = 0
        return

    def begin_page(self, page, ctm):
        (x0, y0, x1, y1) = page.mediabox
        (x0, y0) = apply_matrix_pt(ctm, (x0, y0))
        (x1, y1) = apply_matrix_pt(ctm, (x1, y1))
        mediabox = (0, 0, abs(x0-x1), abs(y0-y1))
        self.cur_item = LTPage(self.pageno, mediabox)
        return

    def end_page(self, page):
        assert not self._stack, str(len(self._stack))
        assert isinstance(self.cur_item, LTPage), str(type(self.cur_item))
        if self.laparams is not None:
            self.cur_item.analyze(self.laparams)
        self.pageno += 1
        self.receive_layout(self.cur_item)
        return

    def begin_figure(self, name, bbox, matrix):
        self._stack.append(self.cur_item)
        self.cur_item = LTFigure(name, bbox, mult_matrix(matrix, self.ctm))
        return

    def end_figure(self, _):
        fig = self.cur_item
        assert isinstance(self.cur_item, LTFigure), str(type(self.cur_item))
        self.cur_item = self._stack.pop()
        self.cur_item.add(fig)
        return

    def render_image(self, name, stream):
        assert isinstance(self.cur_item, LTFigure), str(type(self.cur_item))
        item = LTImage(name, stream,
                       (self.cur_item.x0, self.cur_item.y0,
                        self.cur_item.x1, self.cur_item.y1))
        self.cur_item.add(item)
        return

    def paint_path(self, gstate, stroke, fill, evenodd, path):
        shape = ''.join(x[0] for x in path)
        if shape == 'ml':
            # horizontal/vertical line
            (_, x0, y0) = path[0]
            (_, x1, y1) = path[1]
            (x0, y0) = apply_matrix_pt(self.ctm, (x0, y0))
            (x1, y1) = apply_matrix_pt(self.ctm, (x1, y1))
            if x0 == x1 or y0 == y1:
                self.cur_item.add(LTLine(gstate.linewidth, (x0, y0), (x1, y1),
                    stroke, fill, evenodd, gstate.scolor, gstate.ncolor))
                return
        if shape == 'mlllh':
            # rectangle
            (_, x0, y0) = path[0]
            (_, x1, y1) = path[1]
            (_, x2, y2) = path[2]
            (_, x3, y3) = path[3]
            (x0, y0) = apply_matrix_pt(self.ctm, (x0, y0))
            (x1, y1) = apply_matrix_pt(self.ctm, (x1, y1))
            (x2, y2) = apply_matrix_pt(self.ctm, (x2, y2))
            (x3, y3) = apply_matrix_pt(self.ctm, (x3, y3))
            if ((x0 == x1 and y1 == y2 and x2 == x3 and y3 == y0) or
                (y0 == y1 and x1 == x2 and y2 == y3 and x3 == x0)):
                self.cur_item.add(LTRect(gstate.linewidth, (x0, y0, x2, y2),
                    stroke, fill, evenodd, gstate.scolor, gstate.ncolor))
                return
        # other shapes
        pts = []
        for p in path:
            for i in range(1, len(p), 2):
                pts.append(apply_matrix_pt(self.ctm, (p[i], p[i+1])))
        self.cur_item.add(LTCurve(gstate.linewidth, pts, stroke, fill,
            evenodd, gstate.scolor, gstate.ncolor))
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
        item = LTChar(matrix, font, fontsize, scaling, rise, text, textwidth, textdisp, ncs, graphicstate)
        self.cur_item.add(item)
        return item.adv

    def handle_undefined_char(self, font, cid):
        log.info('undefined: %r, %r', font, cid)
        return '(cid:%d)' % cid

    def receive_layout(self, ltpage):
        return

class TestConverter(PDFLayoutAnalyzer):
    def __init__(self, rsrcmgr, pageno=1):
        laparams = LAParams()
        for param in ("all_texts", "detect_vertical", "word_margin", "char_margin", "line_margin", "boxes_flow"):
            paramv = locals().get(param, None)
            if paramv is not None:
                setattr(laparams, param, paramv)
        PDFLayoutAnalyzer.__init__(self, rsrcmgr, pageno=pageno, laparams=laparams)
        return

    @staticmethod
    def write_text(text):
        text = utils.compatible_encode_method(text, 'utf-8', 'ignore')
        #if six.PY3:
        #    text = text.encode()
        # sys.stdout.write(text)
        return

    # a typical page is 612 x 792 in pts or 8.5 x 11 in inches
    # some common margin conversions: 1in = 72 pts, 0.5in = 36 pts
    # LaTeX margins are probably going to be between 36-72pts
    # anything drawn in the first 0.25 - 0.5 of the page is possibly a title + authors
    # So that is 0 - [198-396] pts
    def receive_layout(self, ltpage):
        def render(item, parent, level):
            if not isinstance(item, LTChar) and not isinstance(item, LTAnno):
                sparent = parent.__class__.__name__ or 'root'
                print(f'{"".join([" "] * level)} -> {item.__class__.__name__} {item.y1 if isinstance(item, LTPage) else ""}')
            if isinstance(item, LTTextLineHorizontal):
                self.write_text(f'{"".join([" "] * level)}      ')
                print(f'{"".join([" "] * level)}      ' + str(item.x0))
                for child in item:
                    self.write_text(child.get_text())
            elif isinstance(item, LTContainer):
                for child in item:
                    render(child, item, level + 1)
            '''
            if isinstance(item, LTChar) or isinstance(item, LTAnno):
                self.write_text(item.get_text())
            elif isinstance(item, LTTextLineHorizontal):
                child = list(item)[0]
                self.write_text(child.fontname + ' ' + '%0.5f' % child.size + '\n') # font
            elif isinstance(item, LTTextBoxHorizontal):
                self.write_text('\n')
            elif isinstance(item, LTImage):
                # do image stuff
                pass
            '''
        render(ltpage, None, 0)
        return