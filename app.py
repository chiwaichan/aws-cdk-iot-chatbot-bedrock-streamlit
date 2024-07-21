#!/usr/bin/env python3
import aws_cdk as cdk
import os

from cdk_stack.pipeline_stack import PipelineStack


app = cdk.App()
PipelineStack(app, "AWSIoTChatbotBedrockStreamlit")

app.synth()