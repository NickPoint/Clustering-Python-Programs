import ast
import os
import numpy as np
from typing import Any
from difflib import SequenceMatcher
import pandas as pd


class SubmissionTransformer(ast.NodeTransformer):
    """
    Class for collecting main code (defined outside of functions) and function definitions
    And cleaning nodes from attributes
    """

    def __init__(self):
        self.funs = {}
        self.main = None
        super(SubmissionTransformer, self).__init__()

    def generic_visit(self, node):
        if hasattr(node, 'ctx'):
            del node.ctx
        return super(SubmissionTransformer, self).generic_visit(node)

    def visit_Module(self, node: ast.Module) -> Any:
        # save main main code as separate function
        self.funs['XAEA_Xii'] = ast.FunctionDef(args=ast.arguments(), body=node.body)
        del node.type_ignores
        self.generic_visit(node)
        return node

    def visit_Call(self, node: ast.Call) -> Any:
        # we substitute module.fun() calls by fun() calls
        if isinstance(node.func, ast.Attribute):
            node.func = ast.Name(node.func.attr)
        # we inject main function body into code
        if hasattr(node.func, 'main'):
            if node.func.id == 'main':
                return self.main.body
        node.args = [
            *node.args,
            *node.keywords
        ]
        del node.keywords
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        if node.name == 'main':
            self.main = node
        else:
            self.funs[node.name] = node
            node.args.args = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
                *node.args.kw_defaults,
                *node.args.defaults
            ]
            del node.args.posonlyargs
            del node.args.kwonlyargs
            del node.args.kw_defaults
            del node.args.defaults
            del node.decorator_list
        del node.name
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        # Remove docstrings and useless constants
        if isinstance(node.value, ast.Str) or isinstance(node.value, ast.Constant):
            return
        super().generic_visit(node)
        return node

    def visit_Import(self, node: ast.Import) -> Any:
        return

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        return

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, str):
            return
        self.generic_visit(node)
        return node

    def visit_arg(self, node: ast.arg) -> Any:
        del node.arg
        self.generic_visit(node)
        return node

    def visit_Name(self, node: ast.Name) -> Any:
        # Since most of the names are variable names, part of other names are standard functions
        # and since some functions can be aliased, we decided to delete names
        del node.id
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        del node.value
        self.generic_visit(node)
        return node

    def visit_Compare(self, node: ast.Compare) -> Any:
        # a <= b is the same as b >= a,
        # we define a discrete order so that reflecting this expression does not change similarity score
        def normalise(operators):
            if node.ops and len(node.ops) == 1 and type(node.ops[0]).__name__ in operators:
                if node.left and node.comparators and len(node.comparators) == 1:
                    left, right = node.left, node.comparators[0]
                    if type(left).__name__ > type(right).__name__:
                        left, right = right, left
                        node.left = left
                        node.comparators = [right]
                        return True
            return False

        normalise('Eq')

        if normalise({'Gt', 'Lt'}):
            node.ops = [{ast.Lt: ast.Gt(), ast.Gt: ast.Lt()}[type(node.ops[0])]]

        if normalise({'GtE', 'LtE'}):
            node.ops = [{ast.LtE: ast.GtE(), ast.GtE: ast.LtE()}[type(node.ops[0])]]

        self.generic_visit(node)
        return node

    def get_functions(self) -> dict[str:list[str]]:
        return self.funs


def diff_generator(a, b):
    for group in SequenceMatcher(None, a, b).get_grouped_opcodes(0):
        for tag, i1, i2, j1, j2 in group:
            if tag in ('replace', 'delete'):
                yield i2 - i1


def diff(a, b):
    """
    For similarity (distance measure) to be symmetric, we check it in both directions
    and pick the closest one (one with lower difference)
    """
    a_to_b = sum(diff_generator(a, b))
    b_to_a = sum(diff_generator(b, a))
    if a_to_b > b_to_a:
        return b_to_a, len(b)
    else:
        return a_to_b, len(a)


def generate_similarity_matrix(pycode_string_list):
    submissions = []
    for i, code_str in enumerate(pycode_string_list):
        # Since we cleaned submissions from invalid ones in data_exploration.ipynb
        # we do no use try-except block here
        code_tree = ast.parse(code_str)
        submission = SubmissionTransformer()
        submission.visit(code_tree)
        main_code = submission.get_functions()
        submissions.append({k: ast.dump(v, indent=4).split('\n') for k, v in main_code.items() if v.body})

    n = len(submissions)
    matrix = np.empty((n, n))

    for i in range(n):
        functions = submissions[i]
        # every other submissions
        for k, functions_other in enumerate(submissions[(i + 1):], start=1):
            # Since similarity is symmetrical distance measure,
            # we need to iterate only over upper right triangle of our matrix and then reflect the similarity
            j = i + k

            accumulator = []
            for fname1, function1 in functions.items():
                if fname1 in functions_other:
                    function2 = functions_other[fname1]
                    different, no_of_lines = diff(function1, function2)
                    similar = no_of_lines - different
                    accumulator.append((similar, no_of_lines))

            # compute similarity
            similar_overall = sum(similar for similar, _ in accumulator)
            total = sum(no_of_lines for _, no_of_lines in accumulator)
            similarity_score = similar_overall / total if total else 0
            # similarity is symmetrical distance measure
            matrix[i][j] = similarity_score
            matrix[j][i] = similarity_score

    # Code is identical to itself
    np.fill_diagonal(matrix, 1.0)
    return matrix


def main():
    for hw in next(os.walk('processed'))[1]:
        # Some students left some tasks unanswered; therefore, we need to collect
        # and group solutions and only then iterate over them
        tasks_submissions = {}
        for student in next(os.walk(f'processed/{hw}'))[1]:
            for script in next(os.walk(f'processed/{hw}/{student}'))[2]:
                if script not in tasks_submissions:
                    tasks_submissions[script] = []
                tasks_submissions[script].append(student)

        if not os.path.exists('matrices'):
            os.mkdir('matrices')

        for script, students in tasks_submissions.items():
            submissions = []
            for student in students:
                path = '/'.join([f'processed/{hw}', student, script])
                with open(path, 'r', encoding='UTF-8') as f:
                    submissions.append(f.read())

            sim_matrix = generate_similarity_matrix(submissions)
            data = pd.DataFrame(sim_matrix, index=students, columns=students)
            print(f'{hw} {script} done!')
            with open(f"matrices/{hw}_{script.split('.')[0]}.csv", 'w') as f:
                # We serialise matrices for the further ease of processing
                data.to_csv(f, index_label="idx")


main()