# Installs xblock-sdk and dependencies needed to run the tests suite.
# Run this script inside a fresh virtual environment.
pip install -e git://github.com/edx/xblock-sdk.git@v0.1.2#egg=xblock-sdk==v0.1.2
cd $VIRTUAL_ENV/src/xblock-sdk/ && pip install -r requirements/base.txt \
                                && pip install -r requirements/test.txt && cd -
pip install -r requirements.txt
