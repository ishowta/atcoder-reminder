rm -rf tmp/data
cp -r test/data tmp/data
python3 generate.py --data_path="tmp/data" /contests/tenka1-2018 /contests/tenka1-2018-beginner
