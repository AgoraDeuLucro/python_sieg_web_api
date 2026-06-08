from setuptools import setup

with open("README.md", "r") as arq:
    readme = arq.read()

setup(name='py_sieg_web',
    version='0.0.2',
    license='MIT License',
    author='Yuri Gomes',
    long_description=readme,
    long_description_content_type="text/markdown",
    author_email='yurialdegomes@gmail.com',
    keywords='sieg web',
    description=u'Wrapper não oficial do Sieg Web',
    packages=['py_sieg_web'],
    install_requires=['requests', 'beautifulsoup4', 'openpyxl'],)