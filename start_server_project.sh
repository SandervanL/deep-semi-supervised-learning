ssh -i C:\Users\sande\.ssh\azure_deeplearning azureuser@102.37.126.87

curl -O https://repo.anaconda.com/archive/Anaconda3-2020.11-Linux-x86_64.sh && \
sha256sum Anaconda3-2020.11-Linux-x86_64.sh | grep -q cf2ff493f11eaad5d09ce2b4feaa5ea90db5174303d5b3fe030e16d29aeef7de && \
chmod +x Anaconda3-2020.11-Linux-x86_64.sh && \
./Anaconda3-2020.11-Linux-x86_64.sh -b -p $HOME/anaconda3 && \
export PATH="$HOME/anaconda3/condabin:$PATH" && \
conda init && \
export ML_DATA_PATH="$HOME/deep-semi-supervised-learning/data" && \
git clone https://github.com/SandervanL/deep-semi-supervised-learning && \
cd deep-semi-supervised-learning && \
git checkout python3_port && \
git pull

ssh -i C:\Users\sande\.ssh\azure_deeplearning azureuser@40.122.115.208