tmux new-session -s training

cd ~/deep-semi-supervised-learning && \
export ML_DATA_PATH="$HOME/deep-semi-supervised-learning/data" && \
export PATH="$HOME/anaconda3/condabin:$PATH" && \
conda create -n deeplearning python=3.8 -y && \
conda activate deeplearning && \
conda install numpy matplotlib theano scipy -y && \
python run_2layer_ssl.py 600 1000 300