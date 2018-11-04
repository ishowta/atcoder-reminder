rm -rf tmp/data_test
cp -r data_test tmp/data_test
python3 generate.py --data_path="data_test" /contests/tenka1-2018 /contests/tenka1-2018-beginner
rm -rf data_test
mv tmp/data_test data_test
