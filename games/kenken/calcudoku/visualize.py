import matplotlib.pyplot as plt
from .game import Calcudoku
import numpy as np


OPERATION_DRAW = {
    'divide': '÷',
    'multiply': 'x',
    'add': '+',
    'subtract': '-',
    'none': '',
    'xor': '^'
}


def save_figure(game: Calcudoku, filename, solution=False):
    size = int(np.sqrt(len(game.board)))

    plt.figure(figsize=(size, size))

    plt.xlim(0, size)
    plt.ylim(0, size)

    plt.xticks([])
    plt.yticks([])

    for i in range(size+1):
        plt.plot([0, size], [i, i], 'k', alpha=0.25)
        plt.plot([i, i], [0, size], 'k', alpha=0.25)

    # Add in the numbers if we are printing the solution
    if solution:
        for i, number in enumerate(game.board):
            x = i // size + 0.5
            y = i % size + 0.5

            plt.text(x, y, str(number), ha='center')

    # Put in the partition lines
    for p in game.partitions:
        coords = [(i // size, i % size) for i in p]

        # For each coordinate we draw a thick box around the edges
        # Not in the partition
        for x, y in coords:
            bordering = [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]
            for border in bordering:
                if border not in coords:
                    if x == border[0]:
                        diff_y = 0
                    else:
                        diff_y = 1

                    if y == border[1]:
                        diff_x = 0
                    else:
                        diff_x = 1

                    draw_x = (x + border[0])/2 + 0.5*diff_y
                    draw_y = (y + border[1])/2 + 0.5*diff_x

                    plt.plot([draw_x, draw_x + diff_x], [draw_y, draw_y + diff_y], 'k', linewidth=2)

    # Add in the operation instructions
    for p, op in zip(game.partitions, game.operations):
        # Always want to draw in the upper left, so start with finding the maximum y of the partition
        coords = [(i // size, i % size) for i in p]
        max_y = max([c[1] for c in coords])
        min_x = min([c[0] for c in coords if c[1] == max_y])

        max_y += 1 # Switch to the top of the cell

        if op[0] in OPERATION_DRAW:
            vis = str(op[1]) + OPERATION_DRAW[op[0]]
            plt.text(min_x + 0.1, max_y - 0.2, vis)

    plt.savefig(filename, bbox_inches='tight')
    pass