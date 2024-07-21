from constructs import Construct
from aws_cdk import (
    Stage
)
from cdk_stack.create_stack import CreateStack

class PipelineStage(Stage):

    def __init__(self, scope: Construct, id: str, resource_prefix: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        service = CreateStack(self, resource_prefix + 'deployed-service')