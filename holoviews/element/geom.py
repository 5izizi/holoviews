import numpy as np

import param

from ..core import Dimension, Dataset, Element2D
from ..streams import BoundsXY


class Geometry(Dataset, Element2D):
    """
    Geometry elements represent a collection of objects drawn in
    a 2D coordinate system. The two key dimensions correspond to the
    x- and y-coordinates in the 2D space, while the value dimensions
    may be used to control other visual attributes of the Geometry
    """

    group = param.String(default='Geometry', constant=True)

    kdims = param.List(default=[Dimension('x'), Dimension('y')],
                       bounds=(2, 2), constant=True, doc="""
        The key dimensions of a geometry represent the x- and y-
        coordinates in a 2D space.""")

    vdims = param.List(default=[], constant=True, doc="""
        Value dimensions can be associated with a geometry.""")

    __abstract = True


class Selection2DExpr(object):
    """
    Mixin class for Cartesian 2D elements to add basic support for
    SelectionExpr streams.
    """

    _selection_streams = (BoundsXY,)

    def _get_selection_expr_for_stream_value(self, **kwargs):
        from ..util.transform import dim

        if kwargs.get('bounds', None) is None:
            return None, None, Rectangles([])

        invert_axes = self.opts.get('plot').kwargs.get('invert_axes', False)

        x0, y0, x1, y1 = kwargs['bounds']

        # Handle invert_xaxis/invert_yaxis
        if y0 > y1:
            y0, y1 = y1, y0
        if x0 > x1:
            x0, x1 = x1, x0

        xdim, ydim = self.dimensions()[:2]
        if invert_axes:
            xdim, ydim = ydim, xdim

        bbox = {xdim.name: (x0, x1), ydim.name: (y0, y1)}
        index_cols = kwargs.get('index_cols')
        if index_cols:
            zip_dim = dim(index_cols[0], unique_zip, *index_cols[1:])
            vals = zip_dim.apply(self.dataset.select(**bbox))
            expr = zip_dim.isin(vals)
            region_element = None
        else:
            selection_expr = (
                (dim(xdim) >= x0) & (dim(xdim) <= x1) &
                (dim(ydim) >= y0) & (dim(ydim) <= y1)
            )
            region_element = Rectangles([kwargs['bounds']])
        return selection_expr, bbox, region_element

    @staticmethod
    def _merge_regions(region1, region2, operation):
        if region1 is None or operation == "overwrite":
            return region2
        return region1.clone(region1.interface.concatenate([region1, region2]))



class Points(Selection2DExpr, Geometry):
    """
    Points represents a set of coordinates in 2D space, which may
    optionally be associated with any number of value dimensions.
    """

    group = param.String(default='Points', constant=True)

    _auto_indexable_1d = True


class VectorField(Selection2DExpr, Geometry):
    """
    A VectorField represents a set of vectors in 2D space with an
    associated angle, as well as an optional magnitude and any number
    of other value dimensions. The angles are assumed to be defined in
    radians and by default the magnitude is assumed to be normalized
    to be between 0 and 1.
    """

    group = param.String(default='VectorField', constant=True)

    vdims = param.List(default=[Dimension('Angle', cyclic=True, range=(0,2*np.pi)),
                                Dimension('Magnitude')], bounds=(1, None))


class Segments(Geometry):
    """
    Segments represent a collection of lines in 2D space.
    """
    group = param.String(default='Segments', constant=True)

    kdims = param.List(default=[Dimension('x0'), Dimension('y0'),
                                Dimension('x1'), Dimension('y1')],
                       bounds=(4, 4), constant=True, doc="""
        Segments represent lines given by x- and y-
        coordinates in 2D space.""")


class Rectangles(Geometry):
    """
    Rectangles represent a collection of axis-aligned rectangles in 2D space.
    """

    group = param.String(default='Rectangles', constant=True)

    kdims = param.List(default=[Dimension('x0'), Dimension('y0'),
                                Dimension('x1'), Dimension('y1')],
                       bounds=(4, 4), constant=True, doc="""
        The key dimensions of the Rectangles element represent the
        bottom-left (x0, y0) and top right (x1, y1) coordinates
        of each box.""")

