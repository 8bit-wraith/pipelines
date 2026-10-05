"""Test the actual handler in isolation without loading plugins or starting a server."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail

class DeletePipelineTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text())
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'delete_pipeline')
        handler.decorator_list = []
        handler.args.defaults = []
        for arg in handler.args.args:
            arg.annotation = None
        self.shutdown = AsyncMock()
        self.remove = Mock()
        self.reload = AsyncMock()
        self.namespace = dict(API_KEY='synthetic-key', HTTPException=HTTPException,
            status=SimpleNamespace(HTTP_401_UNAUTHORIZED=401, HTTP_404_NOT_FOUND=404),
            PIPELINE_MODULES={'known': SimpleNamespace(on_shutdown=self.shutdown)},
            PIPELINE_NAMES={'known': 'known'}, PIPELINES_DIR='/synthetic', reload=self.reload,
            os=SimpleNamespace(path=SimpleNamespace(join=lambda *args: '/'.join(args), exists=Mock(return_value=True)), remove=self.remove))
        exec(compile(ast.Module(body=[handler], type_ignores=[]), '<actual handler>', 'exec'), self.namespace)

    def call(self, name, key='synthetic-key'):
        return asyncio.run(self.namespace['delete_pipeline'](SimpleNamespace(id=name), key))

    def test_unknown_id_returns_404_without_side_effects(self):
        with self.assertRaises(HTTPException) as caught:
            self.call('unknown')
        self.assertEqual(caught.exception.status_code, 404)
        self.remove.assert_not_called()
        self.reload.assert_not_awaited()

    def test_missing_name_returns_404_before_shutdown(self):
        self.namespace['PIPELINE_NAMES'].clear()
        with self.assertRaises(HTTPException) as caught:
            self.call('known')
        self.assertEqual(caught.exception.status_code, 404)
        self.shutdown.assert_not_awaited()
        self.remove.assert_not_called()

    def test_known_id_shuts_down_deletes_and_reloads(self):
        self.assertTrue(self.call('known')['status'])
        self.shutdown.assert_awaited_once()
        self.remove.assert_called_once_with('/synthetic/known.py')
        self.reload.assert_awaited_once()

    def test_wrong_key_rejected_first(self):
        with self.assertRaises(HTTPException) as caught:
            self.call('unknown', 'wrong')
        self.assertEqual(caught.exception.status_code, 401)
        self.remove.assert_not_called()

if __name__ == '__main__':
    unittest.main()
