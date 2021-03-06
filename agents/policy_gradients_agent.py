#
# Copyright (c) 2017 Intel Corporation 
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from agents.policy_optimization_agent import *
import numpy as np
from logger import *
import tensorflow as tf
import matplotlib.pyplot as plt

from utils import *


class PolicyGradientsAgent(PolicyOptimizationAgent):
    def __init__(self, env, tuning_parameters, replicated_device=None, thread_id=0):
        PolicyOptimizationAgent.__init__(self, env, tuning_parameters, replicated_device, thread_id)

        self.last_gradient_update_step_idx = 0

    def learn_from_batch(self, batch):
        # batch contains a list of episodes to learn from
        current_states, next_states, actions, rewards, game_overs, total_returns = self.extract_batch(batch)

        for i in reversed(range(len(total_returns))):
            if self.policy_gradient_rescaler == PolicyGradientRescaler.TOTAL_RETURN:
                total_returns[i] = total_returns[0]
            elif self.policy_gradient_rescaler == PolicyGradientRescaler.FUTURE_RETURN:
                # just take the total return as it is
                pass
            elif self.policy_gradient_rescaler == PolicyGradientRescaler.FUTURE_RETURN_NORMALIZED_BY_EPISODE:
                # we can get a single transition episode while playing Doom Basic, causing the std to be 0
                if self.std_discounted_return != 0:
                    total_returns[i] = (total_returns[i] - self.mean_discounted_return) / self.std_discounted_return
                else:
                    total_returns[i] = 0
            elif self.policy_gradient_rescaler == PolicyGradientRescaler.FUTURE_RETURN_NORMALIZED_BY_TIMESTEP:
                total_returns[i] -= self.mean_return_over_multiple_episodes[i]
            else:
                screen.warning("WARNING: The requested policy gradient rescaler is not available")

        targets = total_returns
        if not self.env.discrete_controls and len(actions.shape) < 2:
            actions = np.expand_dims(actions, -1)

        logger.create_signal_value('Returns Variance', np.std(total_returns), self.task_id)
        logger.create_signal_value('Returns Mean', np.mean(total_returns), self.task_id)

        result = self.main_network.online_network.accumulate_gradients([current_states, actions], targets)
        total_loss = result[0]

        return total_loss

    def choose_action(self, curr_state, phase=RunPhase.TRAIN):
        # convert to batch so we can run it through the network
        observation = np.expand_dims(np.array(curr_state['observation']), 0)
        if self.env.discrete_controls:
            # DISCRETE
            action_values = self.main_network.online_network.predict(observation).squeeze()
            if phase == RunPhase.TRAIN:
                action = self.exploration_policy.get_action(action_values)
            else:
                action = np.argmax(action_values)
            action_value = {"action_probability": action_values[action]}
            self.entropy.add_sample(-np.sum(action_values * np.log(action_values + eps)))
        else:
            # CONTINUOUS
            result = self.main_network.online_network.predict(observation)
            action_values = result[0].squeeze()
            if phase == RunPhase.TRAIN:
                action = self.exploration_policy.get_action(action_values)
            else:
                action = action_values
            action_value = {}

        return action, action_value
