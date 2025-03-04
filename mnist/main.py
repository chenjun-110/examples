from __future__ import print_function
import argparse
import torch
from torch._C import AliasDb
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torch.optim.lr_scheduler import StepLR
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
from torch.utils.tensorboard import SummaryWriter
writer = SummaryWriter('./mnist/tensorboard')

class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, 1)
        self.conv2 = nn.Conv2d(32, 64, 3, 1)
        self.dropout1 = nn.Dropout(0.25)
        self.dropout2 = nn.Dropout(0.5)
        self.fc1 = nn.Linear(9216, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        # x = x           #(64,1,28,28)
        x = self.conv1(x) #(64,32,26,26)
        x = F.relu(x)
        x = self.conv2(x) #(64,64,24,24)
        x = F.relu(x)
        x = F.max_pool2d(x, 2)  #(64,64,12,12)
        x = self.dropout1(x)
        x = torch.flatten(x, 1) #(64,9216)  9216=64*12*12
        x = self.fc1(x)   #(64,128)
        x = F.relu(x)
        x = self.dropout2(x)
        x = self.fc2(x)   #(64,10)
        # output = nn.Softmax(dim=1)(x) #-0.228变-2.478？
        # output = nn.LogSoftmax(dim=1)(x) #-0.228变-2.478？
        output = F.log_softmax(x, dim=1) #-0.228变-2.478？
        return output #(64,10) 64张10分类，最大的是概率最高的分类


def train(args, model, device, train_loader, optimizer, epoch):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):# 938轮 = 6万/64
        #data：(64张,1通道,28,28)图片
        data, target = data.to(device), target.to(device) #target：64个数字是几的10分类标签
        optimizer.zero_grad() #梯度清零
        output = model(data) #前馈
        loss = F.nll_loss(output, target) #平均损失，默认reduction='mean'，batch求和(64)->除64
        loss.backward()      #反馈
        optimizer.step() #更新权重
        # plt.show()
        # plt.imshow(transforms.ToPILImage()(data[0]))
        # writer.add_graph(model,(data,))
        if batch_idx == 0: writer.add_graph(model, (data,))
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss.item()))
            if args.dry_run:
                break

#output max索引位置一样表示匹配。谁规定的？ output[batch_index][target_index]
def test(model, device, test_loader, epoch):
    model.eval()
    test_loss = 0 #epoch求和
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:   #10轮
            data, target = data.to(device), target.to(device)
            output = model(data)           #(1000,1,28,28) -> (1000,10)
            test_loss += F.nll_loss(output, target, reduction='sum').item() #batch求和(1000)
            #底下算手写公式
            pred = output.argmax(dim=1, keepdim=True)  #(1000,1) 最大概率的索引,非独热编码
            target1 = target.view_as(pred) #y跟y^对齐(1000)->(1000,1) 
            bool_tensor = pred.eq(target1) #y跟y^相等，转bool (1000,1)
            tnum = bool_tensor.sum()       #求和 false=0 true=1
            num = tnum.item()              #数字张量转数字
            correct += num

    test_loss /= len(test_loader.dataset) #平均损失=损失和/10000

    writer.add_scalar('test_loss', test_loss, epoch)
    writer.add_scalar('test_zql', 100. * correct / len(test_loader.dataset), epoch)
    writer.flush()

    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset))) #正确率


def main():
    #argparse用于命令行与参数解析
    parser = argparse.ArgumentParser(description='PyTorch MNIST Example')
    parser.add_argument('--batch-size', type=int, default=64, metavar='N',
                        help='input batch size for training (default: 64)')
    parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                        help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=14, metavar='N',
                        help='number of epochs to train (default: 14)')
    parser.add_argument('--lr', type=float, default=1.0, metavar='LR',
                        help='learning rate (default: 1.0)')
    parser.add_argument('--gamma', type=float, default=0.7, metavar='M',
                        help='Learning rate step gamma (default: 0.7)')
    parser.add_argument('--no-cuda', action='store_true', default=False,
                        help='disables CUDA training')
    parser.add_argument('--dry-run', action='store_true', default=False,
                        help='quickly check a single pass')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                        help='how many batches to wait before logging training status')
    parser.add_argument('--save-model', action='store_true', default=False,
                        help='For Saving the current Model')
    args = parser.parse_args() #参数对象。
    use_cuda = not args.no_cuda and torch.cuda.is_available()

    torch.manual_seed(args.seed)#为cpu设随机数种子

    device = torch.device("cuda" if use_cuda else "cpu")

    train_kwargs = {'batch_size': args.batch_size}
    test_kwargs = {'batch_size': args.test_batch_size}
    if use_cuda:
        cuda_kwargs = {'num_workers': 1,
                       'pin_memory': True,
                       'shuffle': True}
        train_kwargs.update(cuda_kwargs)
        test_kwargs.update(cuda_kwargs)

    transform=transforms.Compose([
        transforms.ToTensor(),#神经网络对[0,1]小数更高效
        transforms.Normalize((0.1307,), (0.3081,))#转正态分布，防止多层网络梯度爆炸 [-2.x,5.x]
    ])
    dataset1 = datasets.MNIST('../data', train=True, download=True, transform=transform)
    dataset2 = datasets.MNIST('../data', train=False, transform=transform)
    train_loader = torch.utils.data.DataLoader(dataset1, **train_kwargs)# batch_size=64 控制dataloader的分片
    test_loader  = torch.utils.data.DataLoader(dataset2, **test_kwargs)# batch_size=1000

    model = Net().to(device)

    # p = model.parameters()
    optimizer = optim.Adadelta(model.parameters(), lr=args.lr)
    scheduler = StepLR(optimizer, step_size=1, gamma=args.gamma)

    for epoch in range(1, args.epochs + 1): #一轮
        train(args, model, device, train_loader, optimizer, epoch)#6万图
        test(model, device, test_loader, epoch)#1万图
        scheduler.step() #更新学习率

    # if args.save_model:
    torch.save(model.state_dict(), "mnist_cnn.pt")

def pre():
    with torch.no_grad():
        model = torch.load('mnist_cnn.pt')
        model = Net().to("cuda")
        model.eval()

        image = Image.open('608.png')
        transform = transforms.Compose([
            transforms.Resize([28,28]),
            transforms.Grayscale(num_output_channels=1), # 彩色图像转灰度图像num_output_channels默认1
            transforms.ToTensor(),
            # transforms.Normalize((0.1307,), (0.3081,))
        ])
        data = transform(image)
        # plt.imshow(transforms.ToPILImage()(data))
        # plt.show()
        data = data.to("cuda")
        data = data.view(1,1,28,28)
        output = model(data)           #(n,1,28,28) -> (n,10)
        pred = output.argmax(dim=1, keepdim=True)  #(1000,1) 最大概率的索引,非独热编码
        print('预测结果', pred.item())

if __name__ == '__main__':
    # image = Image.open('./123.jpg')
    # aa = transforms.ToTensor()(image)
    # a1 = np.arange(36,dtype='uint8').reshape((3,4,3))
    # a2 = np.asarray(image)
    # print(a1)
    # print('分割线-----------')
    # print(a2)
    # print(len(a1), len(a2))
    # bb=transforms.ToTensor()(a1)
    # print(bb.data)
    # kk = transforms.ToPILImage()(bb)
    # print(kk)
    # plt.imshow(kk)
    # plt.show()
    # cc=transforms.Normalize((0.1307,), (0.3081,))(aa)
    # print(cc.data)
    # print('分割线--------------')
    pre()
    # main()