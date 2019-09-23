from pdfminer.layout import LTTextContainer, LTContainer, LTAnno, LTTextBoxVertical, IndexAssigner, LTChar, \
    LTTextGroupLRTB, LTTextGroupTBRL, LTTextBoxHorizontal, LTTextLineHorizontal, LTTextLineVertical
from pdfminer.utils import bbox2str, get_bound, apply_matrix_pt, matrix2str, fsplit, Plane, uniq

from sortedcontainers import SortedListWithKey


##  LTLayoutContainer
##
class LTLayoutContainer(LTContainer):

    def __init__(self, bbox):
        LTContainer.__init__(self, bbox)
        self.groups = None
        return

    # group_objects: group text object to textlines.
    def group_objects(self, laparams, objs):
        obj0 = None
        line = None
        for obj1 in objs:
            if obj0 is not None:
                # halign: obj0 and obj1 is horizontally aligned.
                #
                #   +------+ - - -
                #   | obj0 | - - +------+   -
                #   |      |     | obj1 |   | (line_overlap)
                #   +------+ - - |      |   -
                #          - - - +------+
                #
                #          |<--->|
                #        (char_margin)
                halign = (obj0.is_compatible(obj1) and
                          obj0.is_voverlap(obj1) and
                          (min(obj0.height, obj1.height) * laparams.line_overlap <
                           obj0.voverlap(obj1)) and
                          (obj0.hdistance(obj1) <
                           max(obj0.width, obj1.width) * laparams.char_margin))

                # valign: obj0 and obj1 is vertically aligned.
                #
                #   +------+
                #   | obj0 |
                #   |      |
                #   +------+ - - -
                #     |    |     | (char_margin)
                #     +------+ - -
                #     | obj1 |
                #     |      |
                #     +------+
                #
                #     |<-->|
                #   (line_overlap)
                valign = (laparams.detect_vertical and
                          obj0.is_compatible(obj1) and
                          obj0.is_hoverlap(obj1) and
                          (min(obj0.width, obj1.width) * laparams.line_overlap <
                           obj0.hoverlap(obj1)) and
                          (obj0.vdistance(obj1) <
                           max(obj0.height, obj1.height) * laparams.char_margin))

                if ((halign and isinstance(line, LTTextLineHorizontal)) or
                    (valign and isinstance(line, LTTextLineVertical))):
                    line.add(obj1)
                elif line is not None:
                    yield line
                    line = None
                else:
                    if valign and not halign:
                        line = LTTextLineVertical(laparams.word_margin)
                        line.add(obj0)
                        line.add(obj1)
                    elif halign and not valign:
                        line = LTTextLineHorizontal(laparams.word_margin)
                        line.add(obj0)
                        line.add(obj1)
                    else:
                        line = LTTextLineHorizontal(laparams.word_margin)
                        line.add(obj0)
                        yield line
                        line = None
            obj0 = obj1
        if line is None:
            line = LTTextLineHorizontal(laparams.word_margin)
            line.add(obj0)
        yield line
        return

    # group_textlines: group neighboring lines to textboxes.
    def group_textlines(self, laparams, lines):
        plane = Plane(self.bbox)
        plane.extend(lines)
        boxes = {}
        for line in lines:
            neighbors = line.find_neighbors(plane, laparams.line_margin)
            if line not in neighbors: continue
            members = []
            for obj1 in neighbors:
                members.append(obj1)
                if obj1 in boxes:
                    members.extend(boxes.pop(obj1))
            if isinstance(line, LTTextLineHorizontal):
                box = LTTextBoxHorizontal()
            else:
                box = LTTextBoxVertical()
            for obj in uniq(members):
                box.add(obj)
                boxes[obj] = box
        done = set()
        for line in lines:
            if line not in boxes: continue
            box = boxes[line]
            if box in done:
                continue
            done.add(box)
            if not box.is_empty():
                yield box
        return

    # group_textboxes: group textboxes hierarchically.
    def group_textboxes(self, laparams, boxes):
        assert boxes, str((laparams, boxes))

        def dist(obj1, obj2):
            """A distance function between two TextBoxes.

            Consider the bounding rectangle for obj1 and obj2.
            Return its area less the areas of obj1 and obj2,
            shown as 'www' below. This value may be negative.
                    +------+..........+ (x1, y1)
                    | obj1 |wwwwwwwwww:
                    +------+www+------+
                    :wwwwwwwwww| obj2 |
            (x0, y0) +..........+------+
            """
            x0 = min(obj1.x0, obj2.x0)
            y0 = min(obj1.y0, obj2.y0)
            x1 = max(obj1.x1, obj2.x1)
            y1 = max(obj1.y1, obj2.y1)
            return ((x1-x0)*(y1-y0) - obj1.width*obj1.height - obj2.width*obj2.height)

        def isany(obj1, obj2):
            """Check if there's any other object between obj1 and obj2.
            """
            x0 = min(obj1.x0, obj2.x0)
            y0 = min(obj1.y0, obj2.y0)
            x1 = max(obj1.x1, obj2.x1)
            y1 = max(obj1.y1, obj2.y1)
            objs = set(plane.find((x0, y0, x1, y1)))
            return objs.difference((obj1, obj2))

        def key_obj(t):
            (c,d,_,_) = t
            return (c,d)

        dists = SortedListWithKey(key=key_obj)
        for i in range(len(boxes)):
            obj1 = boxes[i]
            for j in range(i+1, len(boxes)):
                obj2 = boxes[j]
                dists.add((0, dist(obj1, obj2), obj1, obj2))
        plane = Plane(self.bbox)
        plane.extend(boxes)
        while dists:
            (c, d, obj1, obj2) = dists.pop(0)
            if c == 0 and isany(obj1, obj2):
                dists.add((1, d, obj1, obj2))
                continue
            if (isinstance(obj1, (LTTextBoxVertical, LTTextGroupTBRL)) or
                isinstance(obj2, (LTTextBoxVertical, LTTextGroupTBRL))):
                group = LTTextGroupTBRL([obj1, obj2])
            else:
                group = LTTextGroupLRTB([obj1, obj2])
            plane.remove(obj1)
            plane.remove(obj2)
            removed = [obj1, obj2]
            to_remove = [ (c,d,obj1,obj2) for (c,d,obj1,obj2) in dists
                      if (obj1 in removed or obj2 in removed) ]
            for r in to_remove:
                dists.remove(r)
            for other in plane:
                dists.add((0, dist(group, other), group, other))
            plane.add(group)
        assert len(plane) == 1, str(len(plane))
        return list(plane)

    def analyze(self, laparams):
        # textobjs is a list of LTChar objects, i.e.
        # it has all the individual characters in the page.
        (textobjs, otherobjs) = fsplit(lambda obj: isinstance(obj, LTChar), self)
        for obj in otherobjs:
            obj.analyze(laparams)
        if not textobjs:
            return
        textlines = list(self.group_objects(laparams, textobjs))
        (empties, textlines) = fsplit(lambda obj: obj.is_empty(), textlines)
        for obj in empties:
            obj.analyze(laparams)
        textboxes = list(self.group_textlines(laparams, textlines))
        if -1 <= laparams.boxes_flow and laparams.boxes_flow <= +1 and textboxes:
            self.groups = self.group_textboxes(laparams, textboxes)
            assigner = IndexAssigner()
            for group in self.groups:
                group.analyze(laparams)
                assigner.run(group)
            textboxes.sort(key=lambda box: box.index)
        else:
            def getkey(box):
                if isinstance(box, LTTextBoxVertical):
                    return (0, -box.x1, box.y0)
                else:
                    return (1, box.y0, box.x0)
            textboxes.sort(key=getkey)
        self._objs = textboxes + otherobjs + empties
        return


##  LTFigure
##
class LTFigure(LTLayoutContainer):

    def __init__(self, name, bbox, matrix):
        self.name = name
        self.matrix = matrix
        (x, y, w, h) = bbox
        bbox = get_bound(apply_matrix_pt(matrix, (p, q))
                         for (p, q) in ((x, y), (x+w, y), (x, y+h), (x+w, y+h)))
        LTLayoutContainer.__init__(self, bbox)
        return

    def __repr__(self):
        return ('<%s(%s) %s matrix=%s>' %
                (self.__class__.__name__, self.name,
                 bbox2str(self.bbox), matrix2str(self.matrix)))

    def analyze(self, laparams):
        if not laparams.all_texts:
            return
        LTLayoutContainer.analyze(self, laparams)
        return


##  LTPage
##
class LTPage(LTLayoutContainer):

    def __init__(self, pageid, bbox, rotate=0):
        LTLayoutContainer.__init__(self, bbox)
        self.pageid = pageid
        self.rotate = rotate
        return

    def __repr__(self):
        return ('<%s(%r) %s rotate=%r>' %
                (self.__class__.__name__, self.pageid,
                 bbox2str(self.bbox), self.rotate))


class LTPageHeader(LTTextContainer):
    def __init__(self, word_margin):
        LTTextContainer.__init__(self)
        self.word_margin = word_margin
        return

    def __repr__(self):
        return ('<%s %s %r>' %
                (self.__class__.__name__, bbox2str(self.bbox),
                 self.get_text()))

    def analyze(self, laparams):
        LTTextContainer.analyze(self, laparams)
        LTContainer.add(self, LTAnno('\n'))
        return

    def find_neighbors(self, plane, ratio):
        raise NotImplementedError


class LTPageFooter(LTTextContainer):
    pass

class LTSectionHeader(LTTextContainer):
    pass

class LTSectionBody(LTTextContainer):
    pass

class LTCitation(LTTextContainer):
    def __init__(self):
        LTTextContainer.__init__(self)
        self.ref = 0
        self.author = []
        self.title = None
        self.venue = None
        self.date = '0000'
        self.link = ''
        return
    pass

class LTEquation(LTTextContainer):
    pass

class LTCaption(LTTextContainer):
    pass


