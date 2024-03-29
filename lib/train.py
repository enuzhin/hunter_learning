import matplotlib.pyplot as plt
import torch, torch.nn as nn
import time 
from IPython import  display
import torch.optim as optim
import numpy as np
import os
import shutil


def select_action(policy,state):
    #Select an action (0 or 1) by running policy model and choosing based on the probabilities in state
    _,_ = policy(torch.Tensor(state)) #state_mu,state_logsigma
    action,log_prob = policy.sample_action()
    # Add log probability of our chosen action to our history    
    if policy.policy_history.dim() != 0:
        policy.policy_history = torch.cat([policy.policy_history, log_prob.unsqueeze(0)], dim=0)
    else:
        policy.policy_history = (log_prob.unsqueeze(0))
    return action


def compute_value_function(policy,gamma):
    
    R = 0
    rewards = []
    
    # Discount future rewards back to the present using gamma
    for r in (policy.reward_episode[::-1]):
        R = r + gamma * R
        rewards.insert(0,R)

    rewards = torch.FloatTensor(rewards)
    
    return rewards
    

def compute_loss(policy, rewards, baseline_rewards=None):
    
    policy.reward_history.append(np.sum(policy.reward_episode))
    # Scale rewards
    if baseline_rewards is None:
        rewards = (rewards - rewards.mean()) / (rewards.std()+1e-10)
    else:
        rewards = rewards - baseline_rewards
        rewards = (rewards - rewards.mean()) / (rewards.std()+1e-10)
    
    # Calculate loss
    loss = (torch.sum(torch.mul(policy.policy_history, rewards).mul(-1), 0))
    
    policy.loss_history.append(loss.data[0])
  
    return loss


def compute_baseline_loss(baseline, rewards, baseline_rewards):
    
    # Calculate loss  
    loss = (rewards-baseline_rewards).pow(2).mean()
    
    baseline.loss_history.append(loss.data[0])
    baseline.reward_history.append(torch.cat(baseline.reward_episode, dim=-1).mean().data)
   
    return loss


def play_episode(policy, env, baseline):
    """play one episode from the initial point"""
    for time in range(1000):
        action = select_action(policy, env.state)
        
        #baseline update
        if baseline is not None:
            baseline_reward = baseline(torch.Tensor(env.state))
            if len(baseline_reward.size())==2:
                baseline.reward_episode.append(baseline_reward.t()) 
            else:
                baseline.reward_episode.append(baseline_reward)
        # Step through environment using chosen action    
        # conmpute reward, renew state
        reward = env.step(action) 
        # Save reward
        policy.reward_episode.append(reward)
        
    
def visualize(env, policy, baseline):
    """visualization for the hunter-victim during learning - used as an argument to function train"""
    
    plt.figure(figsize=(16, 10))

    plt.subplot(221)
    plt.title("reward")
    plt.xlabel("#iteration")
    plt.ylabel("reward")
    plt.plot(policy.reward_history, label = 'reward')

    plt.subplot(222)
    victim = np.array(env.victim_trajectory).T
    plt.plot(victim[0],victim[1], label = 'victim')
    plt.plot(victim[0][0], victim[1][0], 'o', label = 'initiial_victim')
    hunter = np.array(env.hunter_trajectory).T
    plt.plot(hunter[0], hunter[1], label = 'hunter')
    plt.plot(hunter[0][0], hunter[1][0], 'o', label = 'initiial_hunter')
    plt.legend()

    if baseline is not None:
        plt.subplot(223)
        plt.title("baseline_reward")
        plt.xlabel("#iteration")
        plt.ylabel("reward")
        plt.plot(baseline.reward_history, label = 'reward')

        plt.subplot(224)
        plt.title("baseline_loss")
        plt.xlabel("#iteration")
        plt.ylabel("loss")
        plt.plot(baseline.loss_history, label = 'loss')

    plt.show()


def visualize_group(env, policy, baseline):
    """visualization for the group during learning - used as an argument to function train"""
    
    plt.figure(figsize=(16, 10))

    plt.subplot(221)
    plt.title("reward")
    plt.xlabel("#iteration")
    plt.ylabel("reward")
    plt.plot(policy.reward_history, label = 'reward')

    plt.subplot(222)
    hunter = np.array(env.hunter_trajectory).T
    plt.plot(hunter[0], hunter[1], label = 'hunter')
    plt.plot(hunter[0][0], hunter[1][0], 'o', label = 'initiial_hunter')
    plt.legend()

    if baseline is not None:
        plt.subplot(223)
        plt.title("baseline_reward")
        plt.xlabel("#iteration")
        plt.ylabel("reward")
        plt.plot(baseline.reward_history, label = 'reward')

        plt.subplot(224)
        plt.title("baseline_loss")
        plt.xlabel("#iteration")
        plt.ylabel("loss")
        plt.plot(baseline.loss_history, label = 'loss')

    plt.show()
    

def train(policy,env, episodes, learning_rate = 1e-4,betas=(0.9, 0.999),eps = 1e-8, gamma=0.9, verbose=True,
          save_policy=True, batch=1, visualize=visualize_group, baseline=None, dirpath = 'train_models'):
    """

    :param policy: (class) Hunter policy
    :param env: (class) Environment
    :param episodes: (int) number of episodes to learn
    :param learning_rate: (float)
    :param gamma: (float) discounting factor
    :param verbose: (boolean) whether to print results
    :param save_policy: (boolean)
    :param batch: (int) number of batch to propagate
    :param visualize: (function)
    :param baseline: (class) baseline net
    :return:
    """
    
    optimizer = optim.Adam(policy.parameters(), lr=learning_rate,betas = betas, eps = eps)
    
    if baseline is not None: b_optimizer = optim.Adam(baseline.parameters(), lr=1e-3)
    
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath)
    os.mkdir(dirpath)
    
    loss = 0
    for episode in range(0, episodes):
        env.reset() # Reset environment and record the starting state   
        play_episode(policy, env, baseline)        
        
        values = compute_value_function(policy, gamma)
        
        
        if baseline is not None:
            # baseline backprop
            baseline_values = torch.cat(baseline.reward_episode, dim=0)
            b_loss = compute_baseline_loss(baseline, values, baseline_values) 
            b_optimizer.zero_grad()
            b_loss.backward(retain_graph=True)
            b_optimizer.step()
        else:
            baseline_values = None
        
        # policy backprop
        loss += compute_loss(policy, values, baseline_values)
        loss = loss.mean()
        policy.reset_game()    
        if baseline is not None: baseline.reset_game()
            
        #update hunter policy 
        if episode % batch == 0:
            loss /= batch
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            loss = 0

        if save_policy and episode % 100 == 0:
            torch.save(policy,dirpath+'/policy_'+str(episode)+'.p') 
        
        if verbose and episode % 10 == 0:
            
            display.clear_output(wait=True)
            visualize(env, policy, baseline)
            
            print('Episode {} \tLast reward: {:.2f}'.format(episode, policy.reward_history[-1]))
            
            if baseline is not None:
                print('Last reward: {:.2f}'.format(baseline.reward_history[-1]))
  