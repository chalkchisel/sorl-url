import sorl_url
from setuptools import setup, find_packages
from setuptools.command.test import test


class TestCommand(test):
    def run(self):
        from tests.runtests import runtests
        runtests()


setup(
    name='sorl-url',
    version=sorl_url.__version__,
    description='Out-of-band processing for sorl-thumbnail thumbnails.',
    author='Bolster Labs, Inc',
    author_email='opensource@boslterlabs.com',
    license='BSD',
    url='https://github.com/bolster/sorl-url',
    packages=find_packages(exclude=['tests', 'tests.*']),
    include_package_data=True,
    platforms='any',
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Multimedia :: Graphics',
        'Framework :: Django',
    ],
    #cmdclass={"test": TestCommand},
)
