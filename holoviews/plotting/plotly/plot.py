import param

from plotly import tools

from ...core import OrderedDict, NdLayout, AdjointLayout, Empty, HoloMap
from ...core.options import Store
from ..plot import DimensionedPlot, GenericLayoutPlot, GenericCompositePlot
from .renderer import PlotlyRenderer

class PlotlyPlot(DimensionedPlot):
    
    width = param.Integer(default=400)
    height = param.Integer(default=400)

    renderer = PlotlyRenderer

    @property
    def state(self):
        """
        The plotting state that gets updated via the update method and
        used by the renderer to generate output.
        """
        return self.handles['fig']



class LayoutPlot(PlotlyPlot, GenericLayoutPlot):

    def __init__(self, layout, **params):
        super(LayoutPlot, self).__init__(layout, **params)
        self.layout, self.subplots, self.paths = self._init_layout(layout)

    def _get_size(self):
        rows, cols = self.layout.shape
        return cols*self.width*0.8, rows*self.height

    def _init_layout(self, layout):
        # Situate all the Layouts in the grid and compute the gridspec
        # indices for all the axes required by each LayoutPlot.
        gidx = 0
        layout_count = 0
        collapsed_layout = layout.clone(shared_data=False, id=layout.id)
        frame_ranges = self.compute_ranges(layout, None, None)
        frame_ranges = OrderedDict([(key, self.compute_ranges(layout, key, frame_ranges))
                                    for key in self.keys])
        layout_items = layout.grid_items()
        layout_dimensions = layout.kdims if isinstance(layout, NdLayout) else None
        layout_subplots, layouts, paths = {}, {}, {}
        inserts_cols = []
        for r, c in self.coords:
            # Get view at layout position and wrap in AdjointLayout
            key, view = layout_items.get((r, c), (None, None))
            view = view if isinstance(view, AdjointLayout) else AdjointLayout([view])
            layouts[(r, c)] = view
            paths[r, c] = key

            # Compute the layout type from shape
            layout_lens = {1:'Single', 2:'Dual', 3: 'Triple'}
            layout_type = layout_lens.get(len(view), 'Single')

            # Get the AdjoinLayout at the specified coordinate
            positions = AdjointLayoutPlot.layout_dict[layout_type]['positions']

            # Create temporary subplots to get projections types
            # to create the correct subaxes for all plots in the layout
            layout_key, _ = layout_items.get((r, c), (None, None))
            if isinstance(layout, NdLayout) and layout_key:
                layout_dimensions = OrderedDict(zip(layout_dimensions, layout_key))

            # Generate the axes and create the subplots with the appropriate
            # axis objects, handling any Empty objects.
            obj = layouts[(r, c)]
            empty = isinstance(obj.main, Empty)
            if empty:
                obj = AdjointLayout([])
            else:
                layout_count += 1
            subplot_data = self._create_subplots(obj, positions,
                                                 layout_dimensions, frame_ranges,
                                                 num=0 if empty else layout_count)
            subplots, adjoint_layout = subplot_data

            # Generate the AdjointLayoutsPlot which will coordinate
            # plotting of AdjointLayouts in the larger grid
            plotopts = self.lookup_options(view, 'plot').options
            layout_plot = AdjointLayoutPlot(adjoint_layout, layout_type, subplots, **plotopts)
            layout_subplots[(r, c)] = layout_plot
            if layout_key:
                collapsed_layout[layout_key] = adjoint_layout
        return collapsed_layout, layout_subplots, paths


    def _create_subplots(self, layout, positions, layout_dimensions, ranges, num=0):
        """
        Plot all the views contained in the AdjointLayout Object using axes
        appropriate to the layout configuration. All the axes are
        supplied by LayoutPlot - the purpose of the call is to
        invoke subplots with correct options and styles and hide any
        empty axes as necessary.
        """
        subplots = {}
        projections = []
        adjoint_clone = layout.clone(shared_data=False, id=layout.id)
        subplot_opts = dict(adjoined=layout)
        main, main_plot = None, None
        for pos in positions:
            # Pos will be one of 'main', 'top' or 'right' or None
            element = layout.get(pos, None)
            if element is None:
                continue

            # Options common for any subplot
            vtype = element.type if isinstance(element, HoloMap) else element.__class__
            plot_type = Store.registry[self.renderer.backend].get(vtype, None)
            plotopts = self.lookup_options(element, 'plot').options
            side_opts = {}
            if pos != 'main':
                plot_type = AdjointLayoutPlot.registry.get(vtype, plot_type)
                if pos == 'right':
                    side_opts = dict(height=main_plot.height, yaxis='right',
                                     invert_axes=True, width=120, show_labels=['y'],
                                     xticks=2, show_title=False)
                else:
                    side_opts = dict(width=main_plot.width, xaxis='top',
                                     height=120, show_labels=['x'], yticks=2,
                                     show_title=False)

            # Override the plotopts as required
            # Customize plotopts depending on position.
            plotopts = dict(side_opts, **plotopts)
            plotopts.update(subplot_opts)

            if plot_type is None:
                self.warning("Plotly plotting class for %s type not found, object will "
                             "not be rendered." % vtype.__name__)
                continue
            num = num if len(self.coords) > 1 else 0
            subplot = plot_type(element, keys=self.keys,
                                dimensions=self.dimensions,
                                layout_dimensions=layout_dimensions,
                                ranges=ranges, subplot=True,
                                uniform=self.uniform, layout_num=num,
                                **plotopts)
            subplots[pos] = subplot
            if isinstance(plot_type, type) and issubclass(plot_type, GenericCompositePlot):
                adjoint_clone[pos] = subplots[pos].layout
            else:
                adjoint_clone[pos] = subplots[pos].hmap
            if pos == 'main':
                main = element
                main_plot = subplot

        return subplots, adjoint_clone


    def initialize_plot(self, ranges=None):
        ranges = self.compute_ranges(self.layout, self.keys[-1], None)
        plots = [[] for i in range(self.rows)]
        passed_plots = []
        tab_titles = {}
        insert_rows, insert_cols = [], []
        adjoined = False
        for r, c in self.coords:
            subplot = self.subplots.get((r, c), None)
            if subplot is not None:
                subplots = subplot.initialize_plot(ranges=ranges)

                # Computes plotting offsets depending on
                # number of adjoined plots
                offset = sum(r >= ir for ir in insert_rows)
                if len(subplots) > 2:
                    adjoined = True
                    # Add pad column in this position
                    insert_cols.append(c)
                    if r not in insert_rows:
                        # Insert and pad marginal row if none exists
                        plots.insert(r+offset, [None for _ in range(len(plots[r]))])
                        # Pad previous rows
                        for ir in range(r):
                            plots[ir].insert(c+1, None)
                        # Add to row offset
                        insert_rows.append(r)
                        offset += 1
                    # Add top marginal
                    plots[r+offset-1] += [subplots.pop(-1), None]
                elif len(subplots) > 1:
                    adjoined = True
                    # Add pad column in this position
                    insert_cols.append(c)
                    # Pad previous rows
                    for ir in range(r):
                        plots[r].insert(c+1, None)
                    # Pad top marginal if one exists
                    if r in insert_rows:
                        plots[r+offset-1] += 2*[None]
                else:
                    # Pad top marginal if one exists
                    if r in insert_rows:
                        plots[r+offset-1] += [None] * (1+(c in insert_cols))
                plots[r+offset] += subplots
                if len(subplots) == 1 and c in insert_cols:
                    plots[r+offset].append(None)

        rows, cols = len(plots), len(plots[0])
        fig = tools.make_subplots(rows=rows, cols=cols, print_grid=False)
        width, height = self._get_size()
        for r, row in enumerate(plots):
            for c, plot in enumerate(row):
                if plot:
                    fig.append_trace(plot, r+1, c+1)
        fig['layout'].update(height=height, width=width,
                             title=self._format_title(self.keys[-1]))

        self.handles['fig'] = fig
        return self.handles['fig']


class AdjointLayoutPlot(PlotlyPlot, GenericCompositePlot):

    layout_dict = {'Single': {'positions': ['main']},
                   'Dual':   {'positions': ['main', 'right']},
                   'Triple': {'positions': ['main', 'right', 'top']}}

    registry = {}

    def __init__(self, layout, layout_type, subplots, **params):
        # The AdjointLayout ViewableElement object
        self.layout = layout
        # Type may be set to 'Embedded Dual' by a call it grid_situate
        self.layout_type = layout_type
        self.view_positions = self.layout_dict[self.layout_type]['positions']

        # The supplied (axes, view) objects as indexed by position
        super(AdjointLayoutPlot, self).__init__(subplots=subplots, **params)


    def initialize_plot(self, ranges=None):
        """
        Plot all the views contained in the AdjointLayout Object using axes
        appropriate to the layout configuration. All the axes are
        supplied by LayoutPlot - the purpose of the call is to
        invoke subplots with correct options and styles and hide any
        empty axes as necessary.
        """
        adjoined_plots = []
        for pos in ['main', 'right', 'top']:
            # Pos will be one of 'main', 'top' or 'right' or None
            subplot = self.subplots.get(pos, None)
            # If no view object or empty position, disable the axis
            if subplot:
                adjoined_plots.append(subplot.initialize_plot(ranges=ranges))
        if not adjoined_plots: adjoined_plots = [None]
        return adjoined_plots
