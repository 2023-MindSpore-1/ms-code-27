#!/bin/bash


if [ $# != 1 ] && [ $# != 2 ]
then
    echo "bash run_eval.sh  [DATASET_PATH] [PREevalED_CKPT_PATH] "
exit 1
fi


get_real_path(){
  if [ "${1:0:1}" == "/" ]; then
    echo "$1"
  else
    echo "$(realpath -m $PWD/$1)"
  fi
}
ulimit -u unlimited
PATH1=$(get_real_path $1)
PATH2=$(get_real_path $2)

if [ -d "eval" ];
then
    rm -rf ./eval
fi
mkdir ./eval
cp -r ./*.py ./eval
cp -r ./*.yaml ./eval
cp -r ./src ./eval
cd ./eval ||exit

python eval.py --data_path=$PATH1 --checkpoint_file_path=$PATH2 > eval.log 2>&1 &
