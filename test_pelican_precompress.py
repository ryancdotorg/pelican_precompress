# This file is part of the pelican-precompress plugin.
# Copyright 2019-2020 Kurt McKee <contactme@kurtmckee.org>
# Released under the MIT license.

import gzip
import pathlib
import time
from unittest.mock import patch, Mock

import pytest

import pelican_precompress as pp


@pytest.mark.parametrize(
    'installed_modules, expected_settings',
    (
        (set(), {'PRECOMPRESS_GZIP': True, 'PRECOMPRESS_BROTLI': False, 'PRECOMPRESS_ZOPFLI': False}),
        ({'brotli'}, {'PRECOMPRESS_GZIP': True, 'PRECOMPRESS_BROTLI': True, 'PRECOMPRESS_ZOPFLI': False}),
        ({'zopfli'}, {'PRECOMPRESS_GZIP': False, 'PRECOMPRESS_BROTLI': False, 'PRECOMPRESS_ZOPFLI': True}),
        ({'brotli', 'zopfli'}, {'PRECOMPRESS_GZIP': False, 'PRECOMPRESS_BROTLI': True, 'PRECOMPRESS_ZOPFLI': True}),
    ),
)
def test_get_settings_compression_support(installed_modules, expected_settings):
    instance = Mock()
    instance.settings = {'OUTPUT_PATH': ''}

    patches = [
        patch(f'pelican_precompress.{module}', module in installed_modules)
        for module in {'brotli', 'zopfli'}
    ]
    [patch_.start() for patch_ in patches]

    settings = pp.get_settings(instance)
    assert isinstance(settings['OUTPUT_PATH'], pathlib.Path)
    assert settings['PRECOMPRESS_TEXT_EXTENSIONS'] == pp.DEFAULT_TEXT_EXTENSIONS
    assert settings['PRECOMPRESS_OVERWRITE'] is False
    for key, expected_value in expected_settings.items():
        assert settings[key] == expected_value

    [patch_.stop() for patch_ in patches]


def test_get_settings_compression_validation():
    instance = Mock()
    instance.settings = {
        'OUTPUT_PATH': '',
        'PRECOMPRESS_BROTLI': True,
        'PRECOMPRESS_GZIP': True,
        'PRECOMPRESS_ZOPFLI': True,
    }

    log = Mock()
    patches = [
        patch('pelican_precompress.brotli', None),
        patch('pelican_precompress.zopfli', None),
        patch('pelican_precompress.log', log)
    ]
    [patch_.start() for patch_ in patches]

    settings = pp.get_settings(instance)
    assert log.error.call_count == 2

    assert isinstance(settings['OUTPUT_PATH'], pathlib.Path)
    assert settings['PRECOMPRESS_OVERWRITE'] is False
    assert settings['PRECOMPRESS_BROTLI'] is False
    assert settings['PRECOMPRESS_ZOPFLI'] is False
    assert settings['PRECOMPRESS_GZIP'] is True

    [patch_.stop() for patch_ in patches]


@pytest.mark.parametrize(
    'extensions',
    (
        {'.br'},
        {'.gz'},
        {'.br', '.gz'},
        {'abc'},
        {'abc', 'def'},
    )
)
def test_get_settings_extensions_validation(extensions):
    instance = Mock()
    instance.settings = {
        'OUTPUT_PATH': '',
        'PRECOMPRESS_TEXT_EXTENSIONS': extensions | {'.txt'}
    }

    log = Mock()
    patches = [
        patch('pelican_precompress.log', log)
    ]
    [patch_.start() for patch_ in patches]

    settings = pp.get_settings(instance)
    assert log.warning.call_count == len(extensions) + 1
    assert settings['PRECOMPRESS_TEXT_EXTENSIONS'] == {'.txt'}

    [patch_.stop() for patch_ in patches]


def test_compress_with_brotli():
    brotli = pytest.importorskip('brotli')
    data = b'a' * 100
    assert brotli.decompress(pp.compress_with_brotli(data)) == data


def test_compress_with_brotli_error():
    pytest.importorskip('brotli')
    with pytest.raises(pp.FileSizeIncrease):
        pp.compress_with_brotli(b'')


def test_compress_with_zopfli():
    pytest.importorskip('zopfli.gzip')
    data = b'a' * 100
    assert gzip.decompress(pp.compress_with_zopfli(data)) == data


def test_compress_with_zopfli_exception():
    pytest.importorskip('zopfli.gzip')
    with pytest.raises(pp.FileSizeIncrease):
        pp.compress_with_zopfli(b'')


def test_compress_with_gzip():
    data = b'a' * 100
    assert gzip.decompress(pp.compress_with_gzip(data)) == data


def test_compress_with_gzip_exception():
    with pytest.raises(pp.FileSizeIncrease):
        pp.compress_with_gzip(b'')


def test_register():
    with patch('pelican_precompress.pelican', Mock()) as pelican:
        pp.register()
    pelican.signals.finalized.connect.assert_called_once_with(pp.compress_files)


def test_copyrights():
    for pattern in ('*.py', '*.rst', '*.ini'):
        for path in pathlib.Path(__file__).parent.glob(pattern):
            with path.open('r') as file:
                assert f'2019-{time.gmtime().tm_year}' in file.read(100), f'{path.name} has an incorrect copyright date'


def test_compress_files_do_nothing(fs):
    fs.create_file('/test.txt')
    instance = Mock()
    instance.settings = {
        'OUTPUT_PATH': '/',
        'PRECOMPRESS_BROTLI': False,
        'PRECOMPRESS_GZIP': False,
        'PRECOMPRESS_ZOPFLI': False,
    }
    pp.compress_files(instance)
    assert not pathlib.Path('/test.gz').exists()
    assert not pathlib.Path('/test.br').exists()


def test_compress_files_never_overwrite(fs):
    with open('/test.txt', 'wb') as file:
        file.write(b'a' * 100)
    fs.create_file('/test.txt.gz')
    instance = Mock()
    instance.settings = {
        'OUTPUT_PATH': '/',
        'PRECOMPRESS_BROTLI': False,
        'PRECOMPRESS_GZIP': True,
        'PRECOMPRESS_ZOPFLI': False,
    }
    with patch('pelican_precompress.log', Mock()) as log:
        pp.compress_files(instance)
    log.info.assert_called_once()
    assert pathlib.Path('/test.txt.gz').exists()
    assert pathlib.Path('/test.txt.gz').stat().st_size == 0


def test_compress_files_overwrite(fs):
    with open('/test.txt', 'wb') as file:
        file.write(b'a' * 100)
    fs.create_file('/test.txt.gz')
    instance = Mock()
    instance.settings = {
        'OUTPUT_PATH': '/',
        'PRECOMPRESS_OVERWRITE': True,
        'PRECOMPRESS_BROTLI': False,
        'PRECOMPRESS_GZIP': True,
        'PRECOMPRESS_ZOPFLI': False,
    }
    with patch('pelican_precompress.log', Mock()) as log:
        pp.compress_files(instance)
    log.warning.assert_called_once()
    assert pathlib.Path('/test.txt.gz').exists()
    assert pathlib.Path('/test.txt.gz').stat().st_size != 0


def test_compress_files_file_size_increase(fs):
    fs.create_file('/test.txt')
    instance = Mock()
    instance.settings = {
        'OUTPUT_PATH': '/',
        'PRECOMPRESS_BROTLI': False,
        'PRECOMPRESS_GZIP': True,
        'PRECOMPRESS_ZOPFLI': False,
    }
    with patch('pelican_precompress.log', Mock()) as log:
        pp.compress_files(instance)
    log.info.assert_called_once()
    assert not pathlib.Path('/test.txt.gz').exists()


def test_compress_files_success_all_algorithms(fs):
    pytest.importorskip('brotli')
    pytest.importorskip('zopfli')
    with open('/test.txt', 'wb') as file:
        file.write(b'a' * 100)
    instance = Mock()
    instance.settings = {'OUTPUT_PATH': '/'}
    pp.compress_files(instance)
    assert pathlib.Path('/test.txt.br').exists()
    assert pathlib.Path('/test.txt.br').stat().st_size != 0
    assert pathlib.Path('/test.txt.gz').exists()
    assert pathlib.Path('/test.txt.gz').stat().st_size != 0
