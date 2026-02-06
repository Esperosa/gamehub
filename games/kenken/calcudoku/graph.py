

class Graph(object):
    def __init__(self, size: int):
        # Start with one node for every coordinate location on the board
        self._nodes = [Node(i) for i in range(size*size)]

        # Set up the edges for each node
        self._edges = []
        for n in range(size*size):
            x = n // size
            y = n % size

            edges = [(x, y + 1), (x, y - 1), (x + 1, y), (x - 1, y)]

            to_add = []
            for e in edges:
                if e[0] >= 0 and e[0] < size and e[1] >= 0 and e[1] < size:
                    to_add.append(self._nodes[e[0] * size + e[1]])
            self._edges.append(to_add)
        pass

    def merge(self, one, two):

        # Get the unique set of edges that border the merged node
        new_edges = list(set(self._edges[one] + self._edges[two]))

        # Merge them together
        self._nodes[one].add(self._nodes[two])

        # Each node would have had the other one as an edge, so remove these
        new_edges.remove(self._nodes[one])
        new_edges.remove(self._nodes[two])

        # Update the edges on the merged node
        self._edges[one] = new_edges

        # Now we have to update the other node connections so they point to one
        # instead of two
        for edge in self._edges:
            if self._nodes[two] in edge:
                edge.remove(self._nodes[two])

                # There is a possibility where the first node was already inside edges,
                # in this case we do not need to do anything
                if self._nodes[one] not in edge:
                    edge.append(self._nodes[one])

        # Remove the second node from the structure
        del self._nodes[two]
        del self._edges[two]

    @property
    def nodes(self):
        return self._nodes

    @property
    def edges(self):
        return self._edges


class Node(object):
    def __init__(self, start):
        self._coords = [start]

    def __repr__(self):
        return 'Coords: ' + str(self.coords)

    @property
    def coords(self):
        return self._coords

    def add(self, node):
        self._coords += node.coords

    def __eq__(self, other):
        return self.coords == other.coords

    def __hash__(self):
        return hash(str(self.coords))
