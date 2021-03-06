﻿# -*-coding:utf-8-*-
#-------------------------------------------------------------------------------
# Name:        AutoEncoder_multi
# Author:      Yuma Matsuoka
# Created:     2015/12/22
#mnistデータセットを次元圧縮するオートエンコーダーを作成した。
#sparse autoencoderやdenoising autoencoderへの拡張性を持たせた。
#中間層や入力出力データを画像として可視化して学習できているかどうかを確認した。
#-------------------------------------------------------------------------------

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import time, math
import numpy as np
import pylab as plt
from sklearn.datasets import fetch_mldata

class Layer:
    def __init__(self, dim, alpha):
        self.alpha = alpha
        self.dim = dim
        self.data = np.zeros((1, self.dim))
    def forward(self):
        pass
    def backward(self):
        pass
    def updateWeight(self):
        pass

class InputLayer(Layer): #Layerを継承
    def __init__(self, dim, alpha):
        Layer.__init__(self, dim, alpha)

class NeuroLayer(Layer): #Layerを継承
    def __init__(self, dim, preLayer, bias, randMax, randMin, alpha):
        Layer.__init__(self, dim, alpha)
        self.preLayer = preLayer
        self.weight = np.random.rand(self.dim, self.preLayer.dim) * (randMax - randMin) - randMax
        self.bias = np.zeros((1, self.dim))
        self.bias.fill(bias)
        self.preLayer.nextLayer = self
        self.nextLayer = None
        self.diff = np.zeros((1, self.preLayer.dim))
        self.diffWeight = np.zeros((self.dim, self.preLayer.dim))
        self.diffBias = np.zeros((1, self.dim))

    def forward(self):#@override
        temp = np.dot(self.preLayer.data, self.weight.T)
        self.data = temp + self.bias

    def backward(self): #@override
        self.diffWeight += np.dot(self.nextLayer.diff.T, self.preLayer.data)
        self.diffBias += self.nextLayer.diff * 1
        self.diff = np.dot(self.nextLayer.diff, self.weight)

    def updateWeight(self): #@override
        self.bias   -= self.diffBias * self.alpha
        self.weight -= self.diffWeight * self.alpha
        self.diffBias = np.zeros((1, self.dim))
        self.diffWeight = np.zeros((self.dim, self.preLayer.dim))

class HiddenLayer(NeuroLayer):
    def __init__(self, dim, preLayer, bias, randMax, randMin, alpha):
        NeuroLayer.__init__(self, dim, preLayer, bias, randMax, randMin, alpha)

class Sparse_HiddenLayer(HiddenLayer):#backward()を変更
    def __init__(self, dim, preLayer, bias, randMax, randMin, alpha):
        HiddenLayer.__init__(self, dim, preLayer, bias, randMax, randMin, alpha)

    def backward(self): #@override
        #ここのdiffWeightのnp.dot()が違う気がする
        self.diffWeight += np.dot(self.nextLayer.diff.T, self.preLayer.data) + np.dot(self.nextLayer.diffAction.T, self.preLayer.data)#正則化項fxを足す
        self.diffBias += self.nextLayer.diff + self.nextLayer.diffAction #fを足す
        self.diff = np.dot(self.nextLayer.diff, self.weight)

class OutputLayer(NeuroLayer):#forward()を変更
    def __init__(self, dim, preLayer, bias, randMax, randMin, alpha):
        NeuroLayer.__init__(self, dim, preLayer, bias, randMax, randMin, alpha)

    def forward(self):#@override
        #weightを転置する制約を入れる
        temp = np.dot(self.preLayer.data, self.weight.T)#転置
        self.data = temp + self.bias

class ActionLayer(Layer): #Layerを継承
    def __init__(self, preLayer, pre_dim, alpha):#引数のdim = prelayer.dim
        Layer.__init__(self, pre_dim, alpha)
        self.nextLayer = None
        self.preLayer = preLayer
        self.preLayer.nextLayer = self
        self.diff = np.zeros((1, self.preLayer.dim))
        self.diffAction = np.zeros((1, self.preLayer.dim))

    def activation(self, x):
        pass

    def deactivation(self, y):
        pass

    def forward(self):#@override
        self.data = self.activation(self.preLayer.data)

    def backward(self):#override
        self.diffAction = self.deactivation(self.data)
        self.diff = self.nextLayer.diff * self.diffAction
        #self.diff = self.nextLayer.diff * self.deactivation(self.data)

class SigmoidLayer(ActionLayer): #ActionLayerを継承
    def __init__(self, preLayer, pre_dim, alpha):
        ActionLayer.__init__(self, preLayer, pre_dim, alpha)

    def activation(self, x):#@override
        return np.ones(self.dim) / (np.ones(self.dim) + np.exp(-x))

    def deactivation(self, y):#@override
        return y * (np.ones(self.dim) - y)

class ErrorLayer(Layer): #Layerを継承
    def __init__(self,preLayer, pre_dim, alpha):#引数のdim = prelayer.dim
        Layer.__init__(self, pre_dim, alpha)
        self.data = 0.0#@override_２乗誤差はスカラー
        self.target = np.zeros((1, self.dim))
        self.preLayer = preLayer
        self.diff = np.zeros((1, self.preLayer.dim))
        self.preLayer.nextLayer = self

    def forward(self): #@override
        dataSum = np.power(self.preLayer.data - self.target, 2)  # n**2
        self.data += dataSum.sum()

    def backward(self): #@override
        self.diff = 2 * (self.preLayer.data - self.target)

    def updateWeight(self): #@override
        self.data = 0.0

class Sparse_ErrorLayer(ErrorLayer):
    def __init__(self,preLayer, pre_dim, alpha, hiddenActionLayer):#引数のdim = prelayer.dim
        ErrorLayer.__init__(self,preLayer, pre_dim, alpha)
        self.hiddenActionLayer = hiddenActionLayer

    def forward(self): #@override
        dataSum = np.power(self.preLayer.data - self.target, 2) # n**2
        regular_Sum = np.abs(self.preLayer.data)#正則化項の絶対値をとる。ここはノルム？
        self.data += dataSum.sum() + regular_Sum.sum() #中間層の出力を足す

def main():
    start_time = time.clock()

    #separate nomal, denoising, sparse
    noised  = False          #ノイズ付加の有無
    sparse  = False          #中間層スパース性の有無

    #setting
    alpha       = 0.001     #学習係数
    bias_hidden = 0.5       #hiddenLayerのバイアスの大きさ
    bias_output = 0.5       #outputLayerのバイアスの大きさ
    iteration   = 100       #学習の実行回数
    hiddenDim   = 100       #中間層の次元
    randMax     = 0.3
    randMin     = -0.3
    batch       = 100       #バッチサイズ
    epoch       = 1000        #エポック
    train_num   = 6000     #学習に使用するサンプル数,データセット全体は70000サンプル
    noise_ratio = 0.3       #雑音付与の割合
    drop_alpha  = 10      #学習係数を下げる頻度(drop_alphaエポック回ると下げる)

    #出力時のファイル名の作成
    output_name = "alpha=" + str(alpha) + ",dim=" + str(hiddenDim) + ",epoch=" + str(epoch)
    if noised: output_name+=",noised"
    if sparse: output_name+=",sparse"

    #input_file mnistの手書き数字データをロード　70000サンプル、28x28ピクセル
    mnist = fetch_mldata('MNIST original', data_home=".")
    mnist_data = mnist.data
    mnist_data = mnist_data.astype(np.float64)
    mnist_data /= mnist_data.max()
    np.random.shuffle(mnist_data)

    trainingTarget, testTarget = np.split(mnist_data.copy(), [train_num])

    if noised:# Add noise
        for data in mnist_data:
            perm = np.random.permutation(mnist_data.shape[1])[:int(mnist_data.shape[1]*noise_ratio)]
            data[perm] = 0.0

    trainingData, testData = np.split(mnist_data, [train_num])

    #make_layer
    if sparse:
        inputLayer          = InputLayer(len(trainingData[0]), alpha)
        hiddenLayer         = Sparse_HiddenLayer(hiddenDim, inputLayer, bias_hidden, randMax, randMin, alpha)#sparsed
        hiddenActionLayer   = SigmoidLayer(hiddenLayer, hiddenLayer.dim, alpha)
        outputLayer         = OutputLayer(len(trainingTarget[0]), hiddenActionLayer, bias_output, randMax, randMin, alpha)
        outputActionLayer   = SigmoidLayer(outputLayer, outputLayer.dim, alpha)
        errorLayer          = Sparse_ErrorLayer(outputActionLayer, outputActionLayer.dim, alpha, hiddenActionLayer)#sparsed

    else:
        inputLayer          = InputLayer(len(trainingData[0]), alpha)
        hiddenLayer         = HiddenLayer(hiddenDim, inputLayer, bias_hidden, randMax, randMin, alpha)
        hiddenActionLayer   = SigmoidLayer(hiddenLayer, hiddenLayer.dim, alpha)
        outputLayer         = OutputLayer(len(trainingTarget[0]), hiddenActionLayer, bias_output, randMax, randMin, alpha)
        outputActionLayer   = SigmoidLayer(outputLayer, outputLayer.dim, alpha)
        errorLayer          = ErrorLayer(outputActionLayer, outputActionLayer.dim, alpha)

    neuralNetwork = np.array([inputLayer, hiddenLayer, hiddenActionLayer, outputLayer, outputActionLayer, errorLayer])

    #training
    count = 0 #バッチ学習用変数
    flag_epoch = False
    errorData = 0
    errorList = []
    for itr in range(iteration):
        for (d, t) in zip(trainingData, trainingTarget):
            inputLayer.data = np.array([d])
            errorLayer.target = np.array([t])
            for layer in neuralNetwork:
                layer.forward()
            for layer in reversed(neuralNetwork):
                layer.backward()

            count += 1
            if count % batch == 0:
                errorData = errorLayer.data / batch
                errorList.append(errorData)
                for layer in neuralNetwork:
                    layer.updateWeight()

            if count == epoch * batch:#エポックを満たすか、学習データを規定回数回るか
                flag_epoch = True
                break
            if count % (drop_alpha * batch) == 0:
                alpha *= 0.5
        if flag_epoch:
            break

    #culuculate_time 計算時間計測
    elapsed_time = time.clock() - start_time
    print("経過時間(minute)", elapsed_time / 60)

    #output_image
    #入力と出力のペアで画像出力
    pic_size = 28       #出力する画像の縦横サイズ
    output_num = 100    #出力する入出力のペア数
    cnt = 0             #テスト用に使っていく画像の番号
    output_element = []
    plt.figure(figsize=(8, 12))
    for i in range(int(output_num/10)):
        for j in range(10):#入力画像
            plt.subplot(20, 10, cnt+1)
            temp = testTarget[(i*10+j)].reshape(pic_size, pic_size)
            temp = temp[::-1,:]
            plt.xlim(0, pic_size)
            plt.ylim(0, pic_size)
            plt.pcolor(temp)
            plt.gray()
            plt.tick_params(labelbottom="off")
            plt.tick_params(labelleft="off")
            cnt += 1

        for j in range(10):#出力画像
            inputLayer.data = np.array(testData[(i*10+j)])
            errorLayer.target = np.array(testTarget[(i*10+j)])
            for layer in neuralNetwork:
                layer.forward()
            plt.subplot(20, 10, cnt+1)
            temp = outputActionLayer.data.reshape(pic_size, pic_size)#活性化関数で２値化されてる
            #temp = outputLayer.data.reshape(pic_size, pic_size)
            temp = temp[::-1,:]
            plt.xlim(0, pic_size)
            plt.ylim(0, pic_size)
            plt.pcolor(temp)
            plt.gray()
            plt.tick_params(labelbottom="off")
            plt.tick_params(labelleft="off")
            cnt += 1
    #plt.show()
    plt.savefig(output_name+",input_output.png")

    if noised:
        #ノイズ付加画像表示
        plt.figure(figsize=(8, 8))
        for i in range(16):#ノイズありを16枚を表示
            plt.subplot(4,4,i+1)
            temp = trainingData[i].reshape(pic_size, pic_size)
            temp = temp[::-1, :]
            plt.xlim(0, pic_size)
            plt.ylim(0, pic_size)
            plt.pcolor(temp)
            plt.gray()
            plt.tick_params(labelbottom="off")
            plt.tick_params(labelleft="off")
        #plt.show()
        plt.savefig(output_name+",add_noise.png")

        #ノイズ付加なし画像表示
        plt.figure(figsize=(8, 8))
        for i in range(16):#ノイズありを16枚を表示
            plt.subplot(4,4,i+1)
            temp = trainingTarget[i].reshape(pic_size, pic_size)
            temp = temp[::-1, :]
            plt.xlim(0, pic_size)
            plt.ylim(0, pic_size)
            plt.pcolor(temp)
            plt.gray()
            plt.tick_params(labelbottom="off")
            plt.tick_params(labelleft="off")
        #plt.show()
        plt.savefig(output_name+",no_noise.png")

    #中間層の出力(hiddenlayer.data)を画像として画像出力
    image_hldata = math.sqrt(hiddenDim)#出力画像サイズ_中間層の次元数に依存
    cnt = 100
    plt.figure(figsize=(8, 8))
    for i in range(output_num):
            inputLayer.data = np.array(testData[100+i])#上で使ったテストデータの続き->100+i
            errorLayer.target = np.array(testTarget[100+i])
            for layer in neuralNetwork:
                layer.forward()
            plt.subplot(10, 10, i+1)
            #temp = hiddenLayer.data.reshape(image_hldata, image_hldata)
            temp = hiddenActionLayer.data.reshape(image_hldata, image_hldata)
            temp = temp[::-1,:]
            plt.xlim(0, image_hldata)
            plt.ylim(0, image_hldata)
            plt.pcolor(temp)
            plt.gray()
            plt.tick_params(labelbottom="off")
            plt.tick_params(labelleft="off")
    #plt.show()
    plt.savefig(output_name+",hiddenLayer_data.png")

    #重みの出力
    item_num = math.sqrt(hiddenDim)
    #中間層の重みを画像出力
    plt.figure(figsize=(12, 12))
    for i in range(len(hiddenLayer.weight)):
        plt.subplot(math.ceil(len(hiddenLayer.weight) / item_num), item_num, i+1)
        temp = hiddenLayer.weight[i].reshape(pic_size, pic_size)
        temp = temp[::-1, :]
        plt.xlim(0, pic_size)
        plt.ylim(0, pic_size)
        plt.pcolor(temp)
        plt.gray()
        plt.tick_params(labelbottom="off")
        plt.tick_params(labelleft="off")
    #plt.show()
    plt.savefig(output_name+",hidden_weight.png")

    #(転置した)出力層の重みを画像出力
    plt.figure(figsize=(12, 12))
    outputLayerWeight_T = np.array(outputLayer.weight).T
    for i in range(len(outputLayerWeight_T)):
        plt.subplot(math.ceil(len(outputLayerWeight_T) / item_num), item_num, i+1)
        temp = outputLayerWeight_T[i].reshape(pic_size, pic_size)
        temp = temp[::-1, :]
        plt.xlim(0, pic_size)
        plt.ylim(0, pic_size)
        plt.pcolor(temp)
        plt.gray()
        plt.tick_params(labelbottom="off")
        plt.tick_params(labelleft="off")
    #plt.show()
    plt.savefig(output_name+",output_weight.png")

    #中間層出力のヒストグラム_黒い画素の割合を調べる
    plt.figure()
    plt.hist(hiddenActionLayer.data[0], bins=256, range = (0, 1))
    plt.xlabel("brightness")
    plt.ylabel("frequency")
    #plt.show()
    plt.savefig(output_name+",sparse_check.png")

    #出力層の平均誤差の値をヒストグラムで出力
    plt.figure()
    plt.plot(errorList)
    plt.ylim(0, 100)
    plt.xlabel("epoch")
    plt.ylabel("error^2")
    plt.xlim([0, epoch])
    #plt.show()
    plt.savefig(output_name+",error.png")

if __name__ == '__main__':
    main()
