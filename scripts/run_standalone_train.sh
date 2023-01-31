#!/bin/bash


if [ $# != 1 ] && [ $# != 2 ]
then
    echo "bash run_standalone_train.sh  [DATASET_PATH]  "
    echo "bash run_standalone_train.sh  [DATASET_PATH] [PRETRAINED_CKPT_PATH] "
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
if [ $# == 2 ]
then 
    PATH2=$(get_real_path $2)
    fi
if [ -d "train" ];
then
    rm -rf ./train
fi
mkdir ./train
cp -r ./*.py ./train
cp -r ./*.yaml ./train
cp -r ./src ./train
cd ./train ||exit
if [ $# == 1 ]
then
python ./trainer_hmr.py  --data_path=$PATH1 > train.log 2>&1 &
fi
if [ $# == 2 ]
then
python ./trainer_hmr.py  --data_path=$PATH1 --checkpoint_file_path=$PATH2 > train.log 2>&1 &
fi
