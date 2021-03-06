"""Collision tests."""

import pytest

from flask_celery.exceptions import OtherInstanceError
from flask_celery.lock_manager import LockManager
from .tasks import add, mul, sub


PARAMS = [(add, 8), (mul, 16), (sub, 0)]


@pytest.mark.parametrize('task,expected', PARAMS)
def test_basic(task, expected, celery_app, celery_worker):
    """Test no collision."""
    assert expected == task.apply_async(args=(4, 4)).get()


@pytest.mark.parametrize('task,expected', PARAMS)
def test_collision(task, expected, celery_app, celery_worker):
    """Test single-instance collision."""
    manager_instance = list()

    # First run the task and prevent it from removing the lock.
    def new_exit(self, *_):
        manager_instance.append(self)
        return None
    original_exit = LockManager.__exit__
    setattr(LockManager, '__exit__', new_exit)
    assert expected == task.apply_async(args=(4, 4)).get()
    setattr(LockManager, '__exit__', original_exit)
    assert manager_instance[0].is_already_running is True

    # Now run it again.
    with pytest.raises(OtherInstanceError) as e:
        task.apply_async(args=(4, 4)).get()

    if manager_instance[0].include_args:
        assert str(e.value).startswith('Failed to acquire lock, {0}.args.'.format(task.name))
    else:
        assert 'Failed to acquire lock, {0} already running.'.format(task.name) == str(e.value)
    assert manager_instance[0].is_already_running is True

    # Clean up.
    manager_instance[0].reset_lock()
    assert manager_instance[0].is_already_running is False

    # Once more.
    assert expected == task.apply_async(args=(4, 4)).get()


def test_include_args(celery_app, celery_worker):
    """Test single-instance collision with task arguments taken into account."""
    manager_instance = list()
    task = mul

    # First run the tasks and prevent them from removing the locks.
    def new_exit(self, *_):  # noqa: D401
        """Expected to be run twice."""
        manager_instance.append(self)
        return None
    original_exit = LockManager.__exit__
    setattr(LockManager, '__exit__', new_exit)
    assert 16 == task.apply_async(args=(4, 4)).get()
    assert 20 == task.apply_async(args=(5, 4)).get()
    setattr(LockManager, '__exit__', original_exit)
    assert manager_instance[0].is_already_running is True
    assert manager_instance[1].is_already_running is True

    # Now run them again.
    with pytest.raises(OtherInstanceError) as e:
        task.apply_async(args=(4, 4)).get()
    assert str(e.value).startswith('Failed to acquire lock, tests.tasks.mul.args.')
    assert manager_instance[0].is_already_running is True
    with pytest.raises(OtherInstanceError) as e:
        task.apply_async(args=(5, 4)).get()
    assert str(e.value).startswith('Failed to acquire lock, tests.tasks.mul.args.')
    assert manager_instance[1].is_already_running is True

    # Clean up.
    manager_instance[0].reset_lock()
    assert manager_instance[0].is_already_running is False
    manager_instance[1].reset_lock()
    assert manager_instance[1].is_already_running is False

    # Once more.
    assert 16 == task.apply_async(args=(4, 4)).get()
    assert 20 == task.apply_async(args=(5, 4)).get()
