# copyright 2003-2015 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
# contact http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This file is part of astroid.
#
# astroid is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 2.1 of the License, or (at your
# option) any later version.
#
# astroid is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License
# for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with astroid. If not, see <http://www.gnu.org/licenses/>.

import types
import unittest

import six
from six.moves import builtins

from astroid import builder
from astroid.interpreter import util as interpreterutil
from astroid import manager
from astroid import nodes
from astroid import test_utils
from astroid import util


class TestHelpers(unittest.TestCase):

    def setUp(self):
        builtins_name = builtins.__name__
        astroid_manager = manager.AstroidManager()
        self.builtins = astroid_manager.astroid_cache[builtins_name]
        self.manager = manager.AstroidManager()

    def _look_up_in_builtins(self, obj_name):
        return self.builtins.getattr(obj_name)[0]

    def test_object_type(self):
        pairs = [
            ('1', self._look_up_in_builtins('int')),
            ('[]', self._look_up_in_builtins('list')),
            ('{1, 2, 3}', self._look_up_in_builtins('set')),
            ('{1:2, 4:3}', self._look_up_in_builtins('dict')),
            ('type', self._look_up_in_builtins('type')),
            ('object', self._look_up_in_builtins('type')),
            ('object()', self._look_up_in_builtins('object')),
            ('lambda: None', self._look_up_in_builtins(types.FunctionType.__name__)),
            ('len', self._look_up_in_builtins(types.BuiltinFunctionType.__name__)),
            ('None', self._look_up_in_builtins(type(None).__name__)),
            ('import sys\nsys#@', self._look_up_in_builtins(types.ModuleType.__name__)),
        ]
        for code, expected in pairs:
            node = test_utils.extract_node(code)
            objtype = interpreterutil.object_type(node)
            self.assertIs(objtype, expected)

    def test_object_type_classes_and_functions(self):
        ast_nodes = test_utils.extract_node('''
        def generator():
            yield

        class A(object):
            def test(self):
                self #@
            @classmethod
            def cls_method(cls): pass
            @staticmethod
            def static_method(): pass
        A #@
        A() #@
        A.test #@
        A().test #@
        A.cls_method #@
        A().cls_method #@
        A.static_method #@
        A().static_method #@
        generator() #@
        ''')
        from_self = interpreterutil.object_type(ast_nodes[0])
        cls = next(ast_nodes[1].infer())
        self.assertIs(from_self, cls)

        cls_type = interpreterutil.object_type(ast_nodes[1])
        self.assertIs(cls_type, self._look_up_in_builtins('type'))

        instance_type = interpreterutil.object_type(ast_nodes[2])
        cls = next(ast_nodes[2].infer())._proxied
        self.assertIs(instance_type, cls)

        expected_method_types = [
            (ast_nodes[3], types.MethodType.__name__ if six.PY2 else types.FunctionType.__name__),
            (ast_nodes[4], types.MethodType.__name__),
            (ast_nodes[5], types.MethodType.__name__),
            (ast_nodes[6], types.MethodType.__name__),
            (ast_nodes[7], types.FunctionType.__name__),
            (ast_nodes[8], types.FunctionType.__name__),
            (ast_nodes[9], types.GeneratorType.__name__),
        ]
        for node, expected in expected_method_types:
            node_type = interpreterutil.object_type(node)
            expected_type = self._look_up_in_builtins(expected)
            self.assertIs(node_type, expected_type)

    @test_utils.require_version(minver='3.0')
    def test_object_type_metaclasses(self):
        module = builder.parse('''
        import abc
        class Meta(metaclass=abc.ABCMeta):
            pass
        meta_instance = Meta()
        ''')
        meta_type = interpreterutil.object_type(module['Meta'])
        self.assertIs(meta_type, module['Meta'].metaclass())

        meta_instance = next(module['meta_instance'].infer())
        instance_type = interpreterutil.object_type(meta_instance)
        self.assertIs(instance_type, module['Meta'])

    @test_utils.require_version(minver='3.0')
    def test_object_type_most_derived(self):
        node = test_utils.extract_node('''
        class A(type):
            def __new__(*args, **kwargs):
                 return type.__new__(*args, **kwargs)
        class B(object): pass
        class C(object, metaclass=A): pass

        # The most derived metaclass of D is A rather than type.
        class D(B , C): #@
            pass
        ''')
        metaclass = node.metaclass()
        self.assertEqual(metaclass.name, 'A')
        obj_type = interpreterutil.object_type(node)
        self.assertEqual(metaclass, obj_type)

    def test_inference_errors(self):
        node = test_utils.extract_node('''
        from unknown import Unknown
        u = Unknown #@
        ''')
        self.assertEqual(interpreterutil.object_type(node), util.Uninferable)

    def test_object_type_too_many_types(self):
        node = test_utils.extract_node('''
        from unknown import Unknown
        def test(x):
            if x:
                return lambda: None
            else:
                return 1
        test(Unknown) #@
        ''')
        self.assertEqual(interpreterutil.object_type(node), util.Uninferable)

    def test_is_subtype(self):
        ast_nodes = test_utils.extract_node('''
        class int_subclass(int):
            pass
        class A(object): pass #@
        class B(A): pass #@
        class C(A): pass #@
        int_subclass() #@
        ''')
        cls_a = ast_nodes[0]
        cls_b = ast_nodes[1]
        cls_c = ast_nodes[2]
        int_subclass = ast_nodes[3]
        int_subclass = interpreterutil.object_type(next(int_subclass.infer()))
        base_int = self._look_up_in_builtins('int')
        self.assertTrue(interpreterutil.is_subtype(int_subclass, base_int))
        self.assertTrue(interpreterutil.is_supertype(base_int, int_subclass))

        self.assertTrue(interpreterutil.is_supertype(cls_a, cls_b))
        self.assertTrue(interpreterutil.is_supertype(cls_a, cls_c))
        self.assertTrue(interpreterutil.is_subtype(cls_b, cls_a))
        self.assertTrue(interpreterutil.is_subtype(cls_c, cls_a))
        self.assertFalse(interpreterutil.is_subtype(cls_a, cls_b))
        self.assertFalse(interpreterutil.is_subtype(cls_a, cls_b))

    @test_utils.require_version(maxver='3.0')
    def test_is_subtype_supertype_old_style_classes(self):
        cls_a, cls_b = test_utils.extract_node('''
        class A: #@
            pass
        class B(A): #@
            pass
        ''')
        self.assertFalse(interpreterutil.is_subtype(cls_a, cls_b))
        self.assertFalse(interpreterutil.is_subtype(cls_b, cls_a))
        self.assertFalse(interpreterutil.is_supertype(cls_a, cls_b))
        self.assertFalse(interpreterutil.is_supertype(cls_b, cls_a))

    def test_is_subtype_supertype_mro_error(self):
        cls_e, cls_f = test_utils.extract_node('''
        class A(object): pass
        class B(A): pass
        class C(A): pass
        class D(B, C): pass
        class E(C, B): pass #@
        class F(D, E): pass #@
        ''')
        self.assertFalse(interpreterutil.is_subtype(cls_e, cls_f))
        self.assertEqual(interpreterutil.is_subtype(cls_f, cls_e), util.Uninferable)
        self.assertEqual(interpreterutil.is_supertype(cls_e, cls_f), util.Uninferable)
        self.assertFalse(interpreterutil.is_supertype(cls_f, cls_e))

    def test_is_subtype_supertype_unknown_bases(self):
        cls_a, cls_b = test_utils.extract_node('''
        from unknown import Unknown
        class A(Unknown): pass #@
        class B(A): pass #@
        ''')
        self.assertTrue(interpreterutil.is_subtype(cls_b, cls_a))
        self.assertTrue(interpreterutil.is_supertype(cls_a, cls_b))

    def test_is_subtype_supertype_unrelated_classes(self):
        cls_a, cls_b = test_utils.extract_node('''
        class A(object): pass #@
        class B(object): pass #@
        ''')
        self.assertFalse(interpreterutil.is_subtype(cls_a, cls_b))
        self.assertFalse(interpreterutil.is_subtype(cls_b, cls_a))
        self.assertFalse(interpreterutil.is_supertype(cls_a, cls_b))
        self.assertFalse(interpreterutil.is_supertype(cls_b, cls_a))

    def test_is_subtype_supertype_classes_no_type_ancestor(self):
        cls_a = test_utils.extract_node('''
        class A(object): #@
            pass
        ''')
        builtin_type = self._look_up_in_builtins('type')
        self.assertFalse(interpreterutil.is_supertype(builtin_type, cls_a))
        self.assertFalse(interpreterutil.is_subtype(cls_a, builtin_type))

    def test_is_subtype_supertype_classes_metaclasses(self):
        cls_a = test_utils.extract_node('''
        class A(type): #@
            pass
        ''')
        builtin_type = self._look_up_in_builtins('type')
        self.assertTrue(interpreterutil.is_supertype(builtin_type, cls_a))
        self.assertTrue(interpreterutil.is_subtype(cls_a, builtin_type))

    @test_utils.require_version(maxver='3.0')
    def test_old_style_class(self):
        # TODO: what is this test supposed to be testing?  It will crash as-is because it calls helpers.
        cls = test_utils.extract_node('''class A: pass''')
        builtin_type = self._look_up_in_builtins('type')
        self.assertEqual(interpreterutil.object_type(cls), builtin_type)


if __name__ == '__main__':
    unittest.main()