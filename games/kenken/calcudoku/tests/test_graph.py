import numpy as np
from calcudoku.graph import Graph


def test_graph_construction():
    g = Graph(5)


def test_graph_merge():
    g = Graph(5)

    g.merge(0, 1)

    # First check that the newly joined node actually has the 0, 1 coordinates
    np.testing.assert_equal(g.nodes[0].coords, [0, 1])

    # Then make sure that the edges on the new node are correct
    assert g.nodes[1] in g.edges[0]
    assert g.nodes[4] in g.edges[0]
    assert g.nodes[5] in g.edges[0]

    # And finally check that nodes that used to have edges on 1 were correctly
    # Converted back to 0
    assert g.nodes[0] in g.edges[1]
