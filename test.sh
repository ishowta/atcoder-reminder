rm -rf tmp/data
cp -r test/data tmp/data
python3 generate.py --mode="test" /contests/tenka1-2018 /contests/tenka1-2018-beginner
