from constructs import Construct
import os
from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    Duration, 
    CfnParameter,   
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_notifications as s3_notifications,
    aws_athena as athena,
    aws_glue as glue,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_ecs_patterns as ecs_patterns
)
import amazon_textract_idp_cdk_constructs as tcdk


class CreateStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        script_location = os.path.dirname(__file__)

        # Build and push Docker image to ECR repository
        docker_image_asset = ecr_assets.DockerImageAsset(self, "StreamlitDockerImage",
            directory=os.path.join(script_location, '../containers/streamlit')
        )

        image_uri = docker_image_asset.image_uri

        # Define Fargate Task Definition
        fargate_task_definition = ecs.FargateTaskDefinition(self, "StreamlitTaskDefinition", cpu=2048, memory_limit_mib=4096)

        ecr_policy_statement = iam.PolicyStatement(
            actions=[
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability", 
                "ecr:GetDownloadUrlForLayer", 
                "ecr:BatchGetImage" 
            ],
            resources=["*"]
        )
        
        # Attach the policy statement to the task execution role
        fargate_task_definition.add_to_execution_role_policy(ecr_policy_statement)

        athena_policy_statement = iam.PolicyStatement(
            actions=[
                "athena:ListDatabases",
                "athena:ListTableMetadata",
                "athena:GetTableMetadata",
                "athena:GetDatabase",
                "athena:GetWorkGroup",
                "athena:GetQueryExecution",
                "athena:GetQueryResults",
                "athena:StartQueryExecution",
                "athena:StopQueryExecution",
                "glue:GetDatabase",
                "glue:GetDatabases",
                "glue:GetTable",
                "glue:GetTables",
                "glue:GetTableVersion",
                "glue:GetTableVersions",
            ],
            resources=["*"]  # Adjust this based on your resource needs
        )
        fargate_task_definition.add_to_task_role_policy(athena_policy_statement)

        
        # create an s3 bucket as a resource and make it delete files on bucket delete
        s3_bucket_for_athena = s3.Bucket(self,
                                "S3BucketForAthena",
                                versioned=True,
                                removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
        
        s3_bucket_for_athena_bucket_arn = s3_bucket_for_athena.bucket_arn

        s3_bucket_for_athena_s3_path = f"s://{s3_bucket_for_athena.bucket_name}"  


        s3_output_for_athena_policy_statement = iam.PolicyStatement(
            actions=[
                "s3:CreateBucket",
                "s3:GetBucketLocation",
                "s3:ListBucket",
                "s3:ListBucketMultipartUploads",
                "s3:GetObject",
                "s3:AbortMultipartUpload",
                "s3:PutObject",
                "s3:ListMultipartUploadParts"
            ],
            resources=[s3_bucket_for_athena_bucket_arn, f"{s3_bucket_for_athena_bucket_arn}/*"],
        )
        fargate_task_definition.add_to_task_role_policy(s3_output_for_athena_policy_statement)


        bedrock_policy_statement = iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel"
            ],
            resources=["*"],
        )
        fargate_task_definition.add_to_task_role_policy(bedrock_policy_statement)





        container = fargate_task_definition.add_container(
            "StreamlitContainer",
            image=ecs.ContainerImage.from_registry(image_uri),
            memory_limit_mib=4096,
            cpu=2048,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="Streamlit")
        )
        container.add_port_mappings(
            ecs.PortMapping(container_port=8501, protocol=ecs.Protocol.TCP)
        )

        # Define Fargate Service
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(self, "StreamlitFargateService",
            task_definition=fargate_task_definition,
            public_load_balancer=True
        )
        
        
        
        
        # Outputs
        CfnOutput(self, "FargateServiceURL",
            value=fargate_service.load_balancer.load_balancer_dns_name
        )










        iot_device_athena_data_bucket = s3.Bucket(self,
            "IoTDeviceAthenaDataBucket",
            removal_policy=RemovalPolicy.DESTROY,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=True,
        )

        # iot_device_athena_data_bucket_bucket_arn = iot_device_athena_data_bucket.bucket_arn

        iot_device_athena_data_bucket_policy_statement = iam.PolicyStatement(
            actions=[
                "athena:StartQueryExecution",
                "athena:GetQueryExecution",
                "athena:GetQueryResults",
                "athena:ListWorkGroups",
                "athena:GetWorkGroup",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:PutObject",
                "s3:GetBucketLocation"
            ],
            resources=[
                iot_device_athena_data_bucket.bucket_arn, 
                f"{iot_device_athena_data_bucket.bucket_arn}/*"
            ],
        )
        fargate_task_definition.add_to_task_role_policy(iot_device_athena_data_bucket_policy_statement)




        athena_database = glue.CfnDatabase(self,
            "AthenaDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="iot_database"
            )
        )

        athena_table = glue.CfnTable(self,
            "AthenaTable",
            catalog_id=self.account,
            database_name=athena_database.ref,
            table_input=glue.CfnTable.TableInputProperty(
                name="devices",
                table_type="EXTERNAL_TABLE",
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    columns=[ 
                        glue.CfnTable.ColumnProperty(name="device_name", type="string"),
                        glue.CfnTable.ColumnProperty(name="temperature", type="double"),
                        glue.CfnTable.ColumnProperty(name="humidity", type="double"),
                        glue.CfnTable.ColumnProperty(name="accel_x", type="double"),
                        glue.CfnTable.ColumnProperty(name="accel_y", type="double"),
                        glue.CfnTable.ColumnProperty(name="accel_z", type="double"),
                        glue.CfnTable.ColumnProperty(name="timestamp", type="timestamp"),
                    ],
                    location=f"s3://{iot_device_athena_data_bucket.bucket_name}/",
                    input_format="org.apache.hadoop.mapred.TextInputFormat",
                    output_format="org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library="org.openx.data.jsonserde.JsonSerDe"
                    )
                )
            )
        )








        container.add_environment(
            "S3_BUCKET", f's3://{s3_bucket_for_athena.bucket_name}'
        )
        container.add_environment(
            "ATHENA_DATABASE_NAME", athena_database.database_input.name
        )
        