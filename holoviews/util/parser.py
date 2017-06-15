"""
The magics offered by the HoloViews IPython extension are powerful and
support rich, compositional specifications. To avoid the the brittle,
convoluted code that results from trying to support the syntax in pure
Python, this file defines suitable parsers using pyparsing that are
cleaner and easier to understand.

Pyparsing is required by matplotlib and will therefore be available if
HoloViews is being used in conjunction with matplotlib.
"""
from __future__ import division
import param
from itertools import groupby
import numpy as np
import pyparsing as pp

from ..core.options import Options, Cycle, Palette
from ..operation import Compositor

ascii_uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
allowed = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!#$%&\()*+,-./:;<=>?@\\^_`{|}~'


# To generate warning in the standard param style
# Parameterize Parser and use warning method once param supports
# logging at the class level.
class ParserWarning(param.Parameterized):pass
parsewarning = ParserWarning(name='Warning')

class Parser(object):
    """
    Base class for magic line parsers, designed for forgiving parsing
    of keyword lists.
    """

    # Static namespace set in __init__.py of the extension
    namespace = {'np': np, 'Cycle': Cycle, 'Palette': Palette}
    # If True, raise SyntaxError on eval error otherwise warn
    abort_on_eval_failure = False

    @classmethod
    def _strip_commas(cls, kw):
        "Strip out any leading/training commas from the token"
        kw = kw[:-1] if kw[-1]==',' else kw
        return kw[1:] if kw[0]==',' else kw

    @classmethod
    def recurse_token(cls, token, inner):
        recursed = []
        for tok in token:
            if isinstance(tok, list):
                new_tok = [s for t in tok for s in
                           (cls.recurse_token(t, inner)
                            if isinstance(t, list) else [t])]
                recursed.append((inner % ''.join(new_tok)))
            else:
                recursed.append(tok)
        return inner % ''.join(recursed)

    @classmethod
    def collect_tokens(cls, parseresult, mode):
        """
        Collect the tokens from a (potentially) nested parse result.
        """
        inner = '(%s)' if mode=='parens' else '[%s]'
        if parseresult is None: return []
        tokens = []
        for token in parseresult.asList():
            # If value is a tuple, the token will be a list
            if isinstance(token, list):
                token = cls.recurse_token(token, inner)
                tokens[-1] = tokens[-1] + token
            else:
                if token.strip() == ',': continue
                tokens.append(cls._strip_commas(token))
        return tokens

    @classmethod
    def todict(cls, parseresult, mode='parens', ns={}):
        """
        Helper function to return dictionary given the parse results
        from a pyparsing.nestedExpr object (containing keywords).

        The ns is a dynamic namespace (typically the IPython Notebook
        namespace) used to update the class-level namespace.
        """
        grouped, kwargs = [], {}
        tokens = cls.collect_tokens(parseresult, mode)
        # Group tokens without '=' and append to last token containing '='
        for group in groupby(tokens, lambda el: '=' in el):
            (val, items) = group
            if val is True:
                grouped += list(items)
            if val is False:
                elements =list(items)
                # Assume anything before ) or } can be joined with commas
                # (e.g tuples with spaces in them)
                joiner=',' if any(((')' in el) or ('}' in el))
                                  for el in elements) else ''
                grouped[-1] += joiner + joiner.join(elements)

        for keyword in grouped:
            # Tuple ('a', 3) becomes (,'a',3) and '(,' is never valid
            # Same for some of the other joining errors corrected here
            for (fst,snd) in [('(,', '('), ('{,', '{'), ('=,','='),
                              (',:',':'), (':,', ':'), (',,', ','),
                              (',.', '.')]:
                keyword = keyword.replace(fst, snd)
            try:
                kwargs.update(eval('dict(%s)' % keyword,
                                   dict(cls.namespace, **ns)))
            except:
                if cls.abort_on_eval_failure:
                    raise SyntaxError("Could not evaluate keyword: %r"
                                      % keyword)
                msg = "Ignoring keyword pair that fails to evaluate: '%s'"
                parsewarning.warning(msg % keyword)

        return kwargs



class OptsSpec(Parser):
    """
    An OptsSpec is a string specification that describes an
    OptionTree. It is a list of tree path specifications (using dotted
    syntax) separated by keyword lists for any of the style, plotting
    or normalization options. These keyword lists are denoted
    'plot(..)', 'style(...)' and 'norm(...)'  respectively.  These
    three groups may be specified even more concisely using keyword
    lists delimited by square brackets, parentheses and braces
    respectively.  All these sets are optional and may be supplied in
    any order.

    For instance, the following string:

    Image (interpolation=None) plot(show_title=False) Curve style(color='r')

    Would specify an OptionTree where Image has "interpolation=None"
    for style and 'show_title=False' for plot options. The Curve has a
    style set such that color='r'.

    The parser is fairly forgiving; commas between keywords are
    optional and additional spaces are often allowed. The only
    restriction is that keywords *must* be immediately followed by the
    '=' sign (no space).
    """

    plot_options_short = pp.nestedExpr('[',
                                       ']',
                                       content=pp.OneOrMore(pp.Word(allowed) ^ pp.quotedString)
                                   ).setResultsName('plot_options')

    plot_options_long = pp.nestedExpr(opener='plot[',
                                      closer=']',
                                      content=pp.OneOrMore(pp.Word(allowed) ^ pp.quotedString)
                                  ).setResultsName('plot_options')

    plot_options = (plot_options_short | plot_options_long)

    style_options_short = pp.nestedExpr(opener='(',
                                        closer=')',
                                        ignoreExpr=None
                                    ).setResultsName("style_options")

    style_options_long = pp.nestedExpr(opener='style(',
                                       closer=')',
                                       ignoreExpr=None
                                   ).setResultsName("style_options")

    style_options = (style_options_short | style_options_long)


    norm_options_short = pp.nestedExpr(opener='{',
                                       closer='}',
                                       ignoreExpr=None
                                   ).setResultsName("norm_options")

    norm_options_long = pp.nestedExpr(opener='norm{',
                                      closer='}',
                                      ignoreExpr=None
                                  ).setResultsName("norm_options")

    norm_options = (norm_options_short | norm_options_long)

    compositor_ops = pp.MatchFirst(
        [pp.Literal(el.group) for el in Compositor.definitions])

    dotted_path = pp.Combine( pp.Word(ascii_uppercase, exact=1)
                              + pp.Word(pp.alphanums+'._'))


    pathspec = (dotted_path | compositor_ops).setResultsName("pathspec")


    spec_group = pp.Group(pathspec +
                          (pp.Optional(norm_options)
                           & pp.Optional(plot_options)
                           & pp.Optional(style_options)))

    opts_spec = pp.OneOrMore(spec_group)

    # Aliases that map to the current option name for backward compatibility
    aliases = {'horizontal_spacing':'hspace',
               'vertical_spacing':  'vspace',
               'figure_alpha':'    fig_alpha',
               'figure_bounds':   'fig_bounds',
               'figure_inches':   'fig_inches',
               'figure_latex':    'fig_latex',
               'figure_rcparams': 'fig_rcparams',
               'figure_size':     'fig_size',
               'show_xaxis':      'xaxis',
               'show_yaxis':      'yaxis'}

    deprecations = [('GridImage', 'Image')]

    @classmethod
    def process_normalization(cls, parse_group):
        """
        Given a normalization parse group (i.e. the contents of the
        braces), validate the option list and compute the appropriate
        integer value for the normalization plotting option.
        """
        if ('norm_options' not in parse_group): return None
        opts = parse_group['norm_options'][0].asList()
        if opts == []: return None

        options = ['+framewise', '-framewise', '+axiswise', '-axiswise']

        for normopt in options:
            if opts.count(normopt) > 1:
                raise SyntaxError("Normalization specification must not"
                                  " contain repeated %r" % normopt)

        if not all(opt in options for opt in opts):
            raise SyntaxError("Normalization option not one of %s"
                              % ", ".join(options))
        excluded = [('+framewise', '-framewise'), ('+axiswise', '-axiswise')]
        for pair in excluded:
            if all(exclude in opts for exclude in pair):
                raise SyntaxError("Normalization specification cannot"
                                  " contain both %s and %s" % (pair[0], pair[1]))

        # If unspecified, default is -axiswise and -framewise
        if len(opts) == 1 and opts[0].endswith('framewise'):
            axiswise = False
            framewise = True if '+framewise' in opts else False
        elif len(opts) == 1 and opts[0].endswith('axiswise'):
            framewise = False
            axiswise = True if '+axiswise' in opts else False
        else:
            axiswise = True if '+axiswise' in opts else False
            framewise = True if '+framewise' in opts else False

        return dict(axiswise=axiswise,
                    framewise=framewise)


    @classmethod
    def _group_paths_without_options(cls, line_parse_result):
        """
        Given a parsed options specification as a list of groups, combine
        groups without options with the first subsequent group which has
        options.
        A line of the form
            'A B C [opts] D E [opts_2]'
        results in
            [({A, B, C}, [opts]), ({D, E}, [opts_2])]
        """
        active_pathspecs = set()
        for group in line_parse_result:
            active_pathspecs.add(group['pathspec'])

            has_options = (
                'norm_options' in group or
                'plot_options' in group or
                'style_options' in group
            )
            if has_options:
                yield active_pathspecs, group
                active_pathspecs = set()

        if active_pathspecs:
            yield active_pathspecs, {}


    @classmethod
    def _merge_options(cls, old_opts, new_opts):
        """
        Update the old_opts option dictionary with the options defined in
        new_opts. Instead of a shallow update as would be performed by calling
        old_opts.update(new_opts), this updates the dictionaries of all option
        types separately.

        Given two dictionaries
            old_opts = {'a': {'x': 'old', 'y': 'old'}}
        and
            new_opts = {'a': {'y': 'new', 'z': 'new'}, 'b': {'k': 'new'}}
        this returns a dictionary
            {'a': {'x': 'old', 'y': 'new', 'z': 'new'}, 'b': {'k': 'new'}}
        """
        merged = dict(old_opts)

        for option_type, options in new_opts.items():
            if option_type not in merged:
                merged[option_type] = {}

            merged[option_type].update(options)

        return merged

    @classmethod
    def apply_deprecations(cls, path):
        "Convert any potentially deprecated paths and issue appropriate warnings"
        split = path.split('.')
        msg = 'Element {old} deprecated. Use {new} instead.'
        for old, new in cls.deprecations:
            if split[0] == old:
                parsewarning.warning(msg.format(old=old, new=new))
                return '.'.join([new] + split[1:])
        return path


    @classmethod
    def parse(cls, line, ns={}):
        """
        Parse an options specification, returning a dictionary with
        path keys and {'plot':<options>, 'style':<options>} values.
        """
        parses  = [p for p in cls.opts_spec.scanString(line)]
        if len(parses) != 1:
            raise SyntaxError("Invalid specification syntax.")
        else:
            e = parses[0][2]
            processed = line[:e]
            if (processed.strip() != line.strip()):
                raise SyntaxError("Failed to parse remainder of string: %r" % line[e:])

        grouped_paths = cls._group_paths_without_options(cls.opts_spec.parseString(line))
        parse = {}
        for pathspecs, group in grouped_paths:
            options = {}

            normalization = cls.process_normalization(group)
            if normalization is not None:
                options['norm'] = normalization

            if 'plot_options' in group:
                plotopts =  group['plot_options'][0]
                opts = cls.todict(plotopts, 'brackets', ns=ns)
                options['plot'] = {cls.aliases.get(k,k):v for k,v in opts.items()}

            if 'style_options' in group:
                styleopts = group['style_options'][0]
                opts = cls.todict(styleopts, 'parens', ns=ns)
                options['style'] = {cls.aliases.get(k,k):v for k,v in opts.items()}

            for pathspec in pathspecs:
                parse[pathspec] = cls._merge_options(parse.get(pathspec, {}), options)

        return {
            cls.apply_deprecations(path): {
                option_type: Options(**option_pairs)
                for option_type, option_pairs in options.items()
            }
            for path, options in parse.items()
        }



class CompositorSpec(Parser):
    """
    The syntax for defining a set of compositor is as follows:

    [ mode op(spec) [settings] value ]+

    The components are:

    mode      : Operation mode, either 'data' or 'display'.
    group     : Value identifier with capitalized initial letter.
    op        : The name of the operation to apply.
    spec      : Overlay specification of form (A * B) where A and B are
                 dotted path specifications.
    settings  : Optional list of keyword arguments to be used as
                parameters to the operation (in square brackets).
    """

    mode = pp.Word(pp.alphas+pp.nums+'_').setResultsName("mode")

    op = pp.Word(pp.alphas+pp.nums+'_').setResultsName("op")

    overlay_spec = pp.nestedExpr(opener='(',
                                 closer=')',
                                 ignoreExpr=None
                             ).setResultsName("spec")

    value = pp.Word(pp.alphas+pp.nums+'_').setResultsName("value")

    op_settings = pp.nestedExpr(opener='[',
                                closer=']',
                                ignoreExpr=None
                            ).setResultsName("op_settings")

    compositor_spec = pp.OneOrMore(pp.Group(mode + op + overlay_spec + value
                                            + pp.Optional(op_settings)))


    @classmethod
    def parse(cls, line, ns={}):
        """
        Parse compositor specifications, returning a list Compositors
        """
        definitions = []
        parses  = [p for p in cls.compositor_spec.scanString(line)]
        if len(parses) != 1:
            raise SyntaxError("Invalid specification syntax.")
        else:
            e = parses[0][2]
            processed = line[:e]
            if (processed.strip() != line.strip()):
                raise SyntaxError("Failed to parse remainder of string: %r" % line[e:])

        opmap = {op.__name__:op for op in Compositor.operations}
        for group in cls.compositor_spec.parseString(line):

            if ('mode' not in group) or group['mode'] not in ['data', 'display']:
                raise SyntaxError("Either data or display mode must be specified.")
            mode = group['mode']

            kwargs = {}
            operation = opmap[group['op']]
            spec = ' '.join(group['spec'].asList()[0])

            if  group['op'] not in opmap:
                raise SyntaxError("Operation %s not available for use with compositors."
                                  % group['op'])
            if  'op_settings' in group:
                kwargs = cls.todict(group['op_settings'][0], 'brackets', ns=ns)

            definition = Compositor(str(spec), operation, str(group['value']), mode, **kwargs)
            definitions.append(definition)
        return definitions