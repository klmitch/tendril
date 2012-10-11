## Copyright (C) 2012 by Kevin L. Mitchell <klmitch@mit.edu>
##
## This program is free software: you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation, either version 3 of the
## License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see
## <http://www.gnu.org/licenses/>.

import unittest

import gevent
from gevent import event
import mock
import pkg_resources

from tendril import manager


class ManagerForTest(manager.TendrilManager):
    proto = 'test'

    def connect(self, target, acceptor, wrapper=None):
        super(ManagerForTest, self).connect(target, acceptor, wrapper)

    def listener(self, acceptor, wrapper):
        pass


@mock.patch.dict(manager.TendrilManager._managers)
@mock.patch.dict(manager.TendrilManager._tendrils)
@mock.patch.dict(manager.TendrilManager._running_managers)
class TestTendrilManager(unittest.TestCase):
    def test_init(self):
        tm = ManagerForTest()

        self.assertEqual(tm.endpoint, ('', 0))
        self.assertEqual(tm.tendrils, {})
        self.assertEqual(tm.running, False)
        self.assertEqual(tm._local_addr, None)
        self.assertIsInstance(tm._local_addr_event, event.Event)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(tm._listen_thread, None)
        self.assertEqual(tm._manager_key, ('test', ('', 0)))
        self.assertEqual(dict(manager.TendrilManager._managers), {
            ('test', ('', 0)): tm,
        })
        self.assertEqual(manager.TendrilManager._tendrils, {})
        self.assertEqual(manager.TendrilManager._running_managers, {})

    def test_init_endpoint(self):
        tm = ManagerForTest(('127.0.0.1', 8080))

        self.assertEqual(tm.endpoint, ('127.0.0.1', 8080))
        self.assertEqual(tm.tendrils, {})
        self.assertEqual(tm.running, False)
        self.assertEqual(tm._local_addr, None)
        self.assertIsInstance(tm._local_addr_event, event.Event)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(tm._listen_thread, None)
        self.assertEqual(tm._manager_key, ('test', ('127.0.0.1', 8080)))
        self.assertEqual(dict(manager.TendrilManager._managers), {
            ('test', ('127.0.0.1', 8080)): tm,
        })
        self.assertEqual(manager.TendrilManager._tendrils, {})
        self.assertEqual(manager.TendrilManager._running_managers, {})

    def test_init_duplicate(self):
        dummy = mock.Mock()
        manager.TendrilManager._managers[('test', ('', 0))] = dummy

        self.assertRaises(ValueError, ManagerForTest)

    @mock.patch.object(pkg_resources, 'iter_entry_points')
    def test_get_manager_existing(self, mock_iter_entry_points):
        mock_manager = mock.Mock()
        manager.TendrilManager._managers[('test', ('', 0))] = mock_manager

        result = manager.get_manager('TEST')

        self.assertEqual(id(result), id(mock_manager))
        self.assertFalse(mock_iter_entry_points.called)

    @mock.patch.object(pkg_resources, 'iter_entry_points')
    def test_get_manager_noloader(self, mock_iter_entry_points):
        self.assertRaises(ValueError, manager.get_manager, 'test')
        mock_iter_entry_points.assert_called_once_with('tendril.manager',
                                                       'test')

    @mock.patch.object(pkg_resources, 'iter_entry_points')
    def test_get_manager_failedload(self, mock_iter_entry_points):
        mock_iter_entry_points.return_value = [
            mock.Mock(**{"load.side_effect": TypeError}),
        ]

        self.assertRaises(TypeError, manager.get_manager, 'test')
        mock_iter_entry_points.assert_called_once_with('tendril.manager',
                                                       'test')

    @mock.patch.object(pkg_resources, 'iter_entry_points')
    def test_get_manager(self, mock_iter_entry_points):
        loader = mock.Mock()
        mock_iter_entry_points.return_value = [
            mock.Mock(**{"load.side_effect": ImportError}),
            mock.Mock(**{"load.side_effect": pkg_resources.UnknownExtra}),
            mock.Mock(**{"load.return_value": loader}),
        ]

        manager.get_manager('test')

        mock_iter_entry_points.assert_called_once_with('tendril.manager',
                                                       'test')
        for m in mock_iter_entry_points.return_value:
            m.load.assert_called_once_with()
        loader.assert_called_once_with(('', 0))

    @mock.patch.object(pkg_resources, 'iter_entry_points')
    def test_get_manager_endpoint(self, mock_iter_entry_points):
        loader = mock.Mock()
        mock_iter_entry_points.return_value = [
            mock.Mock(**{"load.return_value": loader}),
        ]

        manager.get_manager('test', ('127.0.0.1', 8080))

        mock_iter_entry_points.assert_called_once_with('tendril.manager',
                                                       'test')
        for m in mock_iter_entry_points.return_value:
            m.load.assert_called_once_with()
        loader.assert_called_once_with(('127.0.0.1', 8080))

    def test_track_tendril(self):
        tm = ManagerForTest()
        tendril = mock.Mock(proto='test',
                            _tendril_key=(('127.0.0.1', 8080),
                                          ('127.0.0.2', 8880)))

        tm._track_tendril(tendril)

        self.assertEqual(tm.tendrils, {
            (('127.0.0.1', 8080), ('127.0.0.2', 8880)): tendril,
        })
        self.assertTrue('test' in manager.TendrilManager._tendrils)
        self.assertEqual(dict(manager.TendrilManager._tendrils['test']), {
            (('127.0.0.1', 8080), ('127.0.0.2', 8880)): tendril,
        })

    def test_untrack_tendril(self):
        tm = ManagerForTest()
        tendril = mock.Mock(proto='test',
                            _tendril_key=(('127.0.0.1', 8080),
                                          ('127.0.0.2', 8880)))
        tm.tendrils[tendril._tendril_key] = tendril
        manager.TendrilManager._tendrils['test'] = {
            tendril._tendril_key: tendril,
        }

        tm._untrack_tendril(tendril)

        self.assertEqual(tm.tendrils, {})
        self.assertTrue('test' in manager.TendrilManager._tendrils)
        self.assertEqual(manager.TendrilManager._tendrils['test'], {})

    def test_untrack_tendril_ignores_keyerror(self):
        tm = ManagerForTest()
        tendril = mock.Mock(proto='test',
                            _tendril_key=(('127.0.0.1', 8080),
                                          ('127.0.0.2', 8880)))

        tm._untrack_tendril(tendril)

        self.assertEqual(tm.tendrils, {})
        self.assertFalse('test' in manager.TendrilManager._tendrils)

    def test_contains(self):
        tm = ManagerForTest()
        tendril = mock.Mock(proto='test',
                            _tendril_key=(('127.0.0.1', 8080),
                                          ('127.0.0.2', 8880)))
        tm.tendrils[tendril._tendril_key] = tendril

        self.assertTrue((('127.0.0.1', 8080), ('127.0.0.2', 8880)) in tm)
        self.assertFalse((('127.0.0.1', 8080), ('127.0.0.3', 8880)) in tm)

    def test_getitem(self):
        tm = ManagerForTest()
        tendril = mock.Mock(proto='test',
                            _tendril_key=(('127.0.0.1', 8080),
                                          ('127.0.0.2', 8880)))
        tm.tendrils[tendril._tendril_key] = tendril

        result = tm[tendril._tendril_key]

        self.assertEqual(id(result), id(tendril))

    def test_find_tendril(self):
        tendril = mock.Mock(proto='test',
                            _tendril_key=(('127.0.0.1', 8080),
                                          ('127.0.0.2', 8880)))
        manager.TendrilManager._tendrils['test'] = {
            tendril._tendril_key: tendril,
        }

        result = manager.find_tendril('TEST', tendril._tendril_key)

        self.assertEqual(id(result), id(tendril))

    def test_connect_notrunning(self):
        tm = ManagerForTest()

        self.assertRaises(ValueError, tm.connect, ('127.0.0.1', 8080),
                          'acceptor')

    def test_connect_familymismatch(self):
        tm = ManagerForTest()
        tm.running = True

        self.assertRaises(ValueError, tm.connect, ('::1', 8080), 'acceptor')

    def test_connect_running(self):
        tm = ManagerForTest()
        tm.running = True

        tm.connect(('127.0.0.1', 8080), 'acceptor')

        # Note: verifying that an exception is not raised

    @mock.patch.object(gevent, 'spawn')
    def test_start_running(self, mock_spawn):
        tm = ManagerForTest()
        tm.running = True

        self.assertRaises(ValueError, tm.start)
        self.assertEqual(manager.TendrilManager._running_managers, {})
        self.assertFalse(mock_spawn.called)

    @mock.patch.object(gevent, 'spawn')
    def test_start_identical(self, mock_spawn):
        tm = ManagerForTest()
        manager.TendrilManager._running_managers[tm._manager_key] = tm

        self.assertRaises(ValueError, tm.start)
        self.assertEqual(manager.TendrilManager._running_managers, {
            tm._manager_key: tm,
        })
        self.assertFalse(mock_spawn.called)

    @mock.patch.object(gevent, 'spawn')
    def test_start(self, mock_spawn):
        tm = ManagerForTest()
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event.set()

        tm.start('acceptor', 'wrapper')

        self.assertEqual(tm.running, True)
        self.assertEqual(tm._local_addr, None)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(manager.TendrilManager._running_managers, {
            tm._manager_key: tm,
        })
        self.assertNotEqual(tm._listen_thread, None)
        mock_spawn.assert_called_once_with(tm.listener, 'acceptor', 'wrapper')
        tm._listen_thread.link.assert_called_once_with(tm.stop)

    def test_stop(self):
        tm = ManagerForTest()
        tm.running = True
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event.set()
        manager.TendrilManager._running_managers[tm._manager_key] = tm

        tm.stop()

        self.assertEqual(tm.running, False)
        self.assertEqual(tm._local_addr, None)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(manager.TendrilManager._running_managers, {})

    def test_stop_desync(self):
        tm = ManagerForTest()
        tm.running = True
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event.set()

        tm.stop()

        self.assertEqual(tm.running, False)
        self.assertEqual(tm._local_addr, None)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(manager.TendrilManager._running_managers, {})

    def test_shutdown(self):
        listen_thread = mock.Mock()
        tm = ManagerForTest()
        tm.running = True
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event.set()
        tm._listen_thread = listen_thread
        manager.TendrilManager._running_managers[tm._manager_key] = tm

        tm.shutdown()

        self.assertEqual(tm.tendrils, {})
        self.assertEqual(tm.running, False)
        self.assertEqual(tm._local_addr, None)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(tm._listen_thread, None)
        listen_thread.kill.assert_called_once_with()

    def test_shutdown_desync(self):
        listen_thread = mock.Mock()
        tm = ManagerForTest()
        tm.running = True
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event.set()
        tm._listen_thread = listen_thread

        tm.shutdown()

        self.assertEqual(tm.tendrils, {})
        self.assertEqual(tm.running, False)
        self.assertEqual(tm._local_addr, None)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(tm._listen_thread, None)
        listen_thread.kill.assert_called_once_with()

    def test_shutdown_close(self):
        listen_thread = mock.Mock()
        tendrils = [
            mock.Mock(proto='test',
                      _tendril_key=(('127.0.0.1', 8080),
                                    ('127.0.0.2', 8880))),
            mock.Mock(proto='test',
                      _tendril_key=(('127.0.0.1', 8080),
                                    ('127.0.0.3', 8880))),
            mock.Mock(proto='test',
                      _tendril_key=(('127.0.0.1', 8080),
                                    ('127.0.0.4', 8880))),
        ]

        tm = ManagerForTest()
        tm.running = True
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event.set()
        tm.tendrils.update(dict((t._tendril_key, t) for t in tendrils))
        tm._listen_thread = listen_thread
        manager.TendrilManager._running_managers[tm._manager_key] = tm

        tm.shutdown()

        self.assertEqual(tm.tendrils, {})
        self.assertEqual(tm.running, False)
        self.assertEqual(tm._local_addr, None)
        self.assertFalse(tm._local_addr_event.is_set())
        self.assertEqual(tm._listen_thread, None)
        listen_thread.kill.assert_called_once_with()
        for tend in tendrils:
            tend.close.assert_called_once_with()

    def test_get_local_addr_notrunning(self):
        tm = ManagerForTest()
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event = mock.Mock()

        result = tm.get_local_addr()

        self.assertEqual(result, None)
        self.assertFalse(tm._local_addr_event.wait.called)

    def test_get_local_addr_notset(self):
        tm = ManagerForTest()
        tm.running = True
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event = mock.Mock(**{
            'wait.return_value': False,
        })

        result = tm.get_local_addr('timeout')

        self.assertEqual(result, None)
        tm._local_addr_event.wait.assert_called_once_with('timeout')

    def test_get_local_addr(self):
        tm = ManagerForTest()
        tm.running = True
        tm._local_addr = ('127.0.0.1', 8080)
        tm._local_addr_event = mock.Mock(**{
            'wait.return_value': True,
        })

        result = tm.get_local_addr()

        self.assertEqual(result, ('127.0.0.1', 8080))
        tm._local_addr_event.wait.assert_called_once_with(None)

    @mock.patch.object(manager.TendrilManager, 'get_local_addr',
                       return_value=('127.0.0.1', 8080))
    def test_local_addr_getter(self, mock_get_local_addr):
        tm = ManagerForTest()

        self.assertEqual(tm.local_addr, ('127.0.0.1', 8080))

    def test_local_addr_setter(self):
        tm = ManagerForTest()
        tm._local_addr_event = mock.Mock()

        tm.local_addr = ('127.0.0.1', 8080)

        self.assertEqual(tm._local_addr, ('127.0.0.1', 8080))
        tm._local_addr_event.set.assert_called_once_with()
