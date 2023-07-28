from strawberry.channels import GraphQLWSConsumer
from strawberry.channels.handlers.ws_handler import ChannelsConsumer
from typing import Any
from kante.context import ChannelsWSContext, EnhancendChannelsWSRequest
from authentikate.utils import authenticate_token_or_none
from asgiref.sync import sync_to_async


class KanteWsConsumer(GraphQLWSConsumer):
    pass

    async def get_context(
        self, request: ChannelsConsumer, connection_params: Any
    ) -> ChannelsWSContext:
        auth = await sync_to_async(authenticate_token_or_none)(
            connection_params.get("token", None)
        )
        if auth:
            user = auth.user
            app = auth.app
            scopes = auth.token.scopes
        else:
            user = request.consumer.scope.get("user", None)
            app = request.consumer.scope.get("app", None)
            scopes = None

        print("user", user)
        assignation_id = None
        return ChannelsWSContext(
            request=EnhancendChannelsWSRequest(
                user=user, app=app, assignation_id=assignation_id, scopes=scopes
            ),
            consumer=request,
            connection_params=connection_params,
        )
