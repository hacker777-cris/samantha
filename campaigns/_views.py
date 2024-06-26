from django.conf import settings
from django.http.response import HttpResponse
from django.views.decorators.http import require_http_methods
from rest_framework import exceptions, status, response

from api.views import SamanthaCampaignsAPIView
from api.dowell.user import DowellUser
from .dbobjects import Campaign, CampaignMessage
from .utils import construct_dowell_email_template
from .serializers import CampaignSerializer, CampaignMessageSerializer
from api.utils import _send_mail

from api.database import SamanthaCampaignsDB
from api.dowell.datacube import DowellDatacube
from rest_framework.response import Response
from .helpers import CustomResponse,CampaignHelper
import requests
import time
import os
from .utils import fetch_email


class UserRegistrationView(SamanthaCampaignsAPIView):
    """
    Endpoint for user registration related operations to create a new users collection.
    """
    def append_workspace_id(self, workspace_id):
        """
        Append workspace ID to a text file if it does not already exist.

        :param workspace_id: The workspace ID to be appended.
        """
        workspace_ids = self.get_workspace_ids()  # Retrieve existing workspace IDs
        if workspace_id not in workspace_ids:  # Check if the ID does not already exist
            with open("workspace_ids.txt", "a") as file:
                file.write(workspace_id + "\n")

    def get_workspace_ids(self):
        """
        Retrieve workspace IDs from the text file.

        :return: A list of workspace IDs.
        """
        if os.path.exists("workspace_ids.txt"):
            with open("workspace_ids.txt", "r") as file:
                workspace_ids = file.read().splitlines()
            return workspace_ids
        else:
            # Create the file if it doesn't exist
            with open("workspace_ids.txt", "a"):
                pass
            return []

    def get(self, request):
        """
        Get all collections and check if there's a collection created by the user.

        This method retrieves collections from the database and checks if a collection created by the user exists.

        :param request: The HTTP request object.
        :return: A response containing collection data or a message indicating the status of the operation.
        """
        print("called")
        workspace_id = request.query_params.get("workspace_id", None)
        collection_name = f"{workspace_id}_samantha_campaign"
        user = DowellUser(workspace_id=workspace_id)
        self.append_workspace_id(workspace_id)  # Append workspace ID

        dowell_datacube = DowellDatacube(db_name=SamanthaCampaignsDB.name, dowell_api_key=settings.PROJECT_API_KEY)
        print("called user registered")

        try:
            response = dowell_datacube.fetch(
                _from=collection_name,
            )
            if not response:
                dowell_datacube.create_collection(name=collection_name)
                dowell_datacube.insert(collection_name, data={"database_created": False})
                self.append_workspace_id(workspace_id)  # Append workspace ID
                return Response(
                    {
                        "success": False,
                        "message": f"The collection {collection_name} did not exist in the Database."
                                f"New collection  {collection_name} has been created."
                    }, status=200)
            else:
                database_created = any(item.get('database_created', False) for item in response)
                print(database_created)
                if not database_created:
                    id_not_created = next((item['_id'] for item in response if not item.get('database_created')), None)
                    return Response(
                        {
                            "success": False,
                            "message": "Database not created",
                            "id": id_not_created
                        },
                        status=status.HTTP_200_OK
                    )
                else:
                    response_data = {
                        "success": True,
                        "database_created": database_created,
                        "message": "Database already created"
                    }

                    return Response(
                        data=response_data,
                        status=status.HTTP_200_OK
                    )

        except Exception as err:
            return CustomResponse(False, str(err), None, status.HTTP_501_NOT_IMPLEMENTED)

    def post(self, request):
        """
        Update database with user registration data.

        This method updates the database with user registration data.

        :param request: The HTTP request object.
        :return: A response indicating the success or failure of the database update operation.
        """
        try:
            workspace_id = request.query_params.get("workspace_id")
            if not workspace_id:
                return Response({
                    "success": False,
                    "message": "Workspace ID is required"
                }, status=status.HTTP_400_BAD_REQUEST)

            id = request.data.get("id")
            if not id:
                return Response({
                    "success": False,
                    "message": "ID parameter is required"
                }, status=status.HTTP_400_BAD_REQUEST)

            collection_name = f"{workspace_id}_samantha_campaign"
            user = DowellUser(workspace_id=workspace_id)

            dowell_datacube = DowellDatacube(db_name=SamanthaCampaignsDB.name, dowell_api_key=settings.PROJECT_API_KEY)
            updated = dowell_datacube.update(
                _in=collection_name,
                filter={"_id": id},
                data={"database_created": True}
            )
            print(updated)
            if not updated:  # Check if updated is an empty list
                return Response({
                    "success": True,
                    "database_created": True,
                    "message": "Database updated"
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "success": False,
                    "database_created": False,
                    "message": "Database not updated"
                }, status=status.HTTP_200_OK)

        except Exception as err:
            return Response({
                "success": False,
                "message": str(err)
            }, status=status.HTTP_400_BAD_REQUEST)
class TestEmail(SamanthaCampaignsAPIView):
    def post(self, request, *args, **kwargs):
        try:
            workspace_id = request.query_params.get("workspace_id")
            user = DowellUser(workspace_id=workspace_id)

            campaign_id = request.data.get("campaign_id")
            recipient_address = request.data.get("recipient_address")
            sender_address = request.data.get("sender_address")
            sender_name = "SAMANTHA CAMPAIGN"
            recipient_name = request.data.get("recipient_name")

            message = CampaignMessage.manager.get(
                    campaign_id=campaign_id, 
                    dowell_api_key=settings.PROJECT_API_KEY,
                    workspace_id=workspace_id,
                    wanted="message"
                )
            
            if message:
                subject = message.subject
                body = message.body

                if message.is_html_email:
                    # If the message is HTML, fetch HTML body
                    html_body = fetch_email(message.html_email_link)
                    if html_body:
                        body = html_body

                _send_mail(
                    subject=subject,
                    body=self.construct_dowell_email_template(
                        subject=subject,
                        body=body,
                        unsubscribe_link="https://samanta-campaigns.flutterflow.app/"
                    ),
                    sender_address=sender_address,
                    recipient_address=recipient_address,
                    sender_name=sender_name,
                    recipient_name=recipient_name,
                )
                return response.Response({
                    "success": True,
                    "message": "Email sent"
                }, status=200)
            else:
                return response.Response({
                    "success": False,
                    "message": "No message found for the campaign."
                }, status=400)

        except Exception as e:
            return response.Response({
                "success": False,
                "message": f"Failed to send email. Error: {str(e)}"
            }, status=500)

    

    def construct_dowell_email_template(
        self,
        subject: str,
        body: str,  
        image_url: str = None,
        unsubscribe_link: str = None
    ):
        """
        Convert a text to an samantha campaigns email template

        :param subject: The subject of the email
        :param body: The body of the email. (Can be html too)
        :param recipient: The recipient of the email
        :param image_url: The url of the image to include in the email
        :param unsubscribe_link: The link to unsubscribe from the email
        """
        if not isinstance(subject, str):
            raise TypeError("subject should be of type str")
        if not isinstance(body, str):
            raise TypeError("body should be of type str")
        
        template = """
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>{subject}</title>
        </head>
        <body
            style="
            font-family: Arial, sans-serif;
            background-color: #ffffff;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            "
        >
            <div style="width: 100%; background-color: #ffffff">
            <header
                style="
                color: #fff;
                display: flex;
                text-align: center;
                justify-content: center;
                padding: 5px;
                "
            >
                <img
                src="{image_url}"
                height="140px"
                width="140px"
                style="display: block; margin: 0 auto"
                />
            </header>
            <article style="margin-top: 20px; text-align: center">
                <h2>{subject}</h2>
            </article>

            <main style="padding: 20px">
                <section style="margin: 20px">
                <p
                    style="font-size: 14px; 
                    font-weight: 600;"
                >
                </p>
                {body}  <!-- Body is inserted here -->
                </section>

                {unsubscribe_section}
            </main>
            </div>
        </body>
        </html>
        """
        if unsubscribe_link:
            unsubscribe_section = f"""
            <footer
            style="
                background-color: #005733;
                color: #fff;
                text-align: center;
                padding: 10px;
            "
            >
            <a 
                href="{unsubscribe_link}" 
                style="
                text-decoration: none;
                color: white;
                margin-bottom: 10px;
                display: block;
                "
            >
                Unsubscribe
            </a>
            </footer>
            """
        else:
            unsubscribe_section = ""

        # Wrap each paragraph in <p> tags
        body_paragraphs = "\n".join(f"<p style='font-size: 14px'>{paragraph.strip()}</p>" for paragraph in body.split("\n\n"))

        return template.format(
            subject=subject.title(),
            body=body_paragraphs,  # Replaced body with paragraphs 
            image_url=image_url or "https://dowellfileuploader.uxlivinglab.online/hr/logo-2-min-min.png",
            unsubscribe_section=unsubscribe_section,
        )

class CampaignListCreateAPIView(SamanthaCampaignsAPIView):
    
    def get(self, request, *args, **kwargs):
        """
        Get all campaigns created by the user
        """
        workspace_id = request.query_params.get("workspace_id", None)
        page_size = request.query_params.get("page_size", 16)
        page_number = request.query_params.get("page_number", 1)
        user = DowellUser(workspace_id=workspace_id)
        try:
            page_number = int(page_number)
            page_size = int(page_size)
        except ValueError:
            raise exceptions.NotAcceptable("Invalid page number or page size.")
        
        user = DowellUser(workspace_id=workspace_id)
        print("called")
        campaigns = Campaign.manager.filter(
            creator_id=workspace_id, 
            dowell_api_key="1b834e07-c68b-4bf6-96dd-ab7cdc62f07f", 
            limit=page_size,
            offset=(page_number - 1) * page_size,
            workspace_id=workspace_id
        )
        data = []

        necessities = (
            "id", "title", "type", "image",
            "broadcast_type", "start_date", 
            "end_date", "is_active", "has_launched"
        )
        for campaign in campaigns:
            campaign_data = campaign.data
            campaign_data = { key: campaign_data[key] for key in necessities }
            data.append(campaign_data)
        
        response_data = {
            "count": len(data),
            "page_size": page_size,
            "page_number": page_number,
            "results": data,
        }
        if page_number > 1:
            response_data["previous_page"] = f"{request.path}?workspace_id={workspace_id}&page_size={page_size}&page_number={page_number - 1}"
        if len(data) == page_size:
            response_data["next_page"] = f"{request.path}?workspace_id={workspace_id}&page_size={page_size}&page_number={page_number + 1}"

        return response.Response(
            data=response_data, 
            status=status.HTTP_200_OK
        )
    

    def post(self, request, *args, **kwargs):
        """
        Create a new campaign

        Request Body Format:
        ```
        {               
            "type": "",
            "broadcast_type": "",
            "title": "",
            "purpose": "",
            "image": "",
            "keyword": "",
            "target_city": "",
            "target_audience": "",
            "range": 100,
            "frequency": "",
            "start_date": "",
            "end_date": "",
            "audiences": [],
            "leads_links": []
        }
        ```
        """
        start_time = time.time()
        workspace_id = request.query_params.get("workspace_id", None)
        user = DowellUser(workspace_id=workspace_id)
        data = request.data
        if not isinstance(data, dict):
            raise exceptions.NotAcceptable("Request body must be a dictionary.")
        
        user = DowellUser(workspace_id=workspace_id)
        data['default_message'] = True
        serializer = CampaignSerializer(
            data=data, 
            context={
                "creator": user,
                "dowell_api_key": settings.PROJECT_API_KEY
            }
        )
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save()

        default_message= {
            "subject": campaign.title,
            "body": campaign.purpose,
            "is_default": True
        }
        message_serializer = CampaignMessageSerializer(
            data=default_message,
            context={
                "campaign": campaign,
                "workspace_id":workspace_id,
                "dowell_api_key": settings.PROJECT_API_KEY
            }
        )
        message_serializer.is_valid(raise_exception=True)

        message_serializer.save()
        
        print("save is okay")
        
        updated_campaign: Campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign.pkey, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )
        print("update is also okay")
        serializer = CampaignSerializer(
            instance=updated_campaign, 
            context={"dowell_api_key": settings.PROJECT_API_KEY},
        )

        can_launch, reason, percentage_ready = updated_campaign.is_launchable(dowell_api_key=settings.PROJECT_API_KEY)

        # updated_campaign = Campaign.manager.get(

        # )

        # can_launch, reason, percentage_ready = campaign.is_launchable(dowell_api_key=settings.PROJECT_API_KEY)
        data = {
            **updated_campaign.data,
            "launch_status": {
                "can_launch": can_launch,
                "reason": reason,
                "percentage_ready": percentage_ready
            }
        }
        
        end_time = time.time()

        print(f"Campaign View: {end_time-start_time}")

        return response.Response(
            data=data,
            status=status.HTTP_200_OK
        )



class CampaignRetrieveUpdateDeleteAPIView(SamanthaCampaignsAPIView):
    """Campaign Retrieve and Update API View"""

    def get(self, request, *args, **kwargs):
        """
        Retrieve a campaign by id
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        campaign: Campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )
        serializer = CampaignSerializer(
            instance=campaign, 
            context={"dowell_api_key": settings.PROJECT_API_KEY}
        )

        can_launch, reason, percentage_ready = campaign.is_launchable(dowell_api_key=settings.PROJECT_API_KEY)
        data = {
            **serializer.data,
            "next_due_date": campaign.next_due_date,
            "has_audiences": campaign.has_audiences,
            "has_message": campaign.get_message(dowell_api_key=settings.PROJECT_API_KEY) is not None,
            "launch_status": {
                "can_launch": can_launch,
                "reason": reason,
                "percentage_ready": percentage_ready
            }
        }
        return response.Response(
            data=data, 
            status=status.HTTP_200_OK
        )


    def put(self, request, *args, **kwargs):
        """
        Update a campaign
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        data = request.data
        if not isinstance(data, dict):
            raise exceptions.NotAcceptable("Request body must be a dictionary.")
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        campaign: Campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )
        print("getting campaign worked")
        serializer = CampaignSerializer(
            instance=campaign, 
            data=data, 
            context={"dowell_api_key": settings.PROJECT_API_KEY}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        print("after saving")
        return response.Response(
            data=serializer.data, 
            status=status.HTTP_200_OK
        )
    

    def patch(self, request, *args, **kwargs):
        """
        Partially update a campaign
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        data = request.data
        if not isinstance(data, dict):
            raise exceptions.NotAcceptable("Request body must be a dictionary.")
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")

        user = DowellUser(workspace_id=workspace_id)
        campaign: Campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )
        
        serializer = CampaignSerializer(
            instance=campaign, 
            data=data, 
            partial=True, 
            context={"dowell_api_key": settings.PROJECT_API_KEY,"workspace_id":workspace_id}
        )
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save()
        
        can_launch, reason, percentage_ready = campaign.is_launchable(dowell_api_key=settings.PROJECT_API_KEY)
        data = {
            **campaign.data,
            "launch_status": {
                "can_launch": can_launch,
                "reason": reason,
                "percentage_ready": percentage_ready
            }
        }
        return response.Response(
            data=data,
            status=status.HTTP_200_OK
        )


    def delete(self, request, *args, **kwargs):
        """
        Delete a campaign
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        campaign: Campaign = Campaign.manager.get(creator_id=workspace_id, pkey=campaign_id, dowell_api_key=settings.PROJECT_API_KEY,workspace_id=workspace_id)
        campaign.delete(dowell_api_key=settings.PROJECT_API_KEY)

        return response.Response(
            data={
                "detail": "Campaign deleted successfully."
            },
            status=status.HTTP_200_OK
        )



class CampaignActivateDeactivateAPIView(SamanthaCampaignsAPIView):
    """Campaign Activate and Deactivate API View"""

    def get(self, request, *args, **kwargs):
        """
        Activate or deactivate campaign
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
    
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        campaign: Campaign = Campaign.manager.get(
            creator_id=workspace_id,
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )

        if campaign.is_active:
            campaign.deactivate(dowell_api_key=settings.PROJECT_API_KEY)
            msg = f"Campaign: '{campaign.title}', has been deactivated."
        else:
            campaign.activate(dowell_api_key=settings.PROJECT_API_KEY)
            msg = f"Campaign: '{campaign.title}', has been activated."
            
        return response.Response(
            data={
                "detail": msg
            },
            status=status.HTTP_200_OK
        )   



class CampaignAudienceListAddAPIView(SamanthaCampaignsAPIView):
    """Campaign Audience List API View"""

    def get(self, request, *args, **kwargs):
        """
        Get all campaign audiences
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )
        
        return response.Response(
            data=campaign.data["audiences"], 
            status=status.HTTP_200_OK
        )

    
    def post(self, request, *args, **kwargs):
        """
        Add audiences to a campaign

        Request Body Format:
        ```
        {
            "audiences": []
        }
        ```
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        data = request.data
        if not isinstance(data, dict):
            raise exceptions.NotAcceptable("Request body must be a dictionary.")
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")

        audiences = data.get("audiences", [])
        if not isinstance(audiences, list):
            raise exceptions.NotAcceptable("Audiences must be a list")
        if not audiences:
            raise exceptions.NotAcceptable("Audiences must be provided.")

        user = DowellUser(workspace_id=workspace_id)
        campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )

        for audience in audiences:
            campaign.add_audience(audience)
        campaign.save(dowell_api_key=settings.PROJECT_API_KEY)

        return response.Response(
            data=campaign.data["audiences"], 
            status=status.HTTP_200_OK
        )


#todo add workspace_id
@require_http_methods(["GET"])
def campaign_audience_unsubscribe_view(request, *args, **kwargs):
    """
    Unsubscribes an audience from a campaign
    """
    campaign_id = kwargs.get("campaign_id", None)
    audience_id = request.GET.get("audience_id", None)
    msg = "You have successfully unsubscribed from this campaign."

    try:
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        if not audience_id:
            raise exceptions.NotAcceptable("Audience id must be provided.")

        campaign = Campaign.manager.get(
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY
        )

        audience = campaign.audiences.get(id=audience_id)
        try:
            audience.unsubscribe()
        except:
            msg = "You have already been unsubscribed from this campaign."
        finally:
            campaign.save(dowell_api_key=settings.PROJECT_API_KEY)

    except:
        msg = "<h3>Something went wrong! Please check the link and try again.</h3>"
        return HttpResponse(msg, status=400)

    html_response = construct_dowell_email_template(
        subject=f"Unsubscribe from Campaign: '{campaign.title}'",
        body=msg,
        recipient=audience.email
    )
    return HttpResponse(html_response, status=200)





class CampaignMessageCreateRetreiveAPIView(SamanthaCampaignsAPIView):
    """Campaign Message Create and Retrieve API View"""

    def get(self, request, *args, **kwargs):
        """
        Get campaign message 
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        message = CampaignMessage.manager.get(
            campaign_id=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id,
            wanted="message"
        )

        return response.Response(
            data=message.data, 
            status=status.HTTP_200_OK
        )
    
    
    def post(self, request, *args, **kwargs):
        """
        Add a message to a campaign

        Request Body Format:
        ```
        {
            "subject": "",
            "body": "",
            "sender": ""
            "is_default": "",
            "is_html_email: "",
            "html_email_link": "",
        }
        ```
        """
        workspace_id = request.query_params.get("workspace_id", None)
        user = DowellUser(workspace_id=workspace_id)
        data = request.data
        if not isinstance(data, dict):
            raise exceptions.NotAcceptable("Request body must be a dictionary.")
        
        campaign_id = kwargs.get("campaign_id", None)
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )

        serializer = CampaignMessageSerializer(
            data=data, 
            context={
                "campaign": campaign,
                "dowell_api_key": settings.PROJECT_API_KEY
            }
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return response.Response(
            data=serializer.data, 
            status=status.HTTP_200_OK
        )




class CampaignMessageUpdateDeleteAPIView(SamanthaCampaignsAPIView):
    """Update and Delete Campaign Message API View"""

    def put(self, request, *args, **kwargs):
        """
        Update campaign message
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        message_id = kwargs.get("message_id", None)
        user = DowellUser(workspace_id=workspace_id)
        data = request.data
        if not isinstance(data, dict):
            raise exceptions.NotAcceptable("Request body must be a dictionary.")
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        if not message_id:
            raise exceptions.NotAcceptable("Message id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        message = CampaignMessage.manager.get(
            pkey=message_id, 
            campaign_id=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id,
            wanted="message"
        )
        
        serializer = CampaignMessageSerializer(
            instance=message, 
            data=data, 
            context={"dowell_api_key": settings.PROJECT_API_KEY,"workspace_id":workspace_id}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        campaign: Campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )

        campaign.default_message = False
        campaign.save(dowell_api_key=settings.PROJECT_API_KEY)

        return response.Response(
            data=serializer.data, 
            status=status.HTTP_200_OK
        )


    def patch(self, request, *args, **kwargs):
        """
        Partially update campaign message
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        message_id = kwargs.get("message_id", None)
        user = DowellUser(workspace_id=workspace_id)
        data = request.data
        if not isinstance(data, dict):
            raise exceptions.NotAcceptable("Request body must be a dictionary.")
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        if not message_id:
            raise exceptions.NotAcceptable("Message id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        message = CampaignMessage.manager.get(
            pkey=message_id, 
            campaign_id=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id,
            wanted = "message"
        )
        
        serializer = CampaignMessageSerializer(
            instance=message, data=data, 
            partial=True, 
            context={"dowell_api_key": settings.PROJECT_API_KEY,"workspace_id":workspace_id}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        campaign: Campaign = Campaign.manager.get(
            creator_id=workspace_id, 
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )

        campaign.default_message = False
        campaign.save(dowell_api_key=settings.PROJECT_API_KEY)

        return response.Response(
            data=serializer.data, 
            status=status.HTTP_200_OK
        )



class CampaignLaunchAPIView(SamanthaCampaignsAPIView):

    def get(self, request, *args, **kwargs):
        """
        Launch a campaign 
        """
        workspace_id = request.query_params.get("workspace_id", None)
        campaign_id = kwargs.get("campaign_id", None)
        user = DowellUser(workspace_id=workspace_id)
        if not campaign_id:
            raise exceptions.NotAcceptable("Campaign id must be provided.")
        
        user = DowellUser(workspace_id=workspace_id)
        campaign = Campaign.manager.get(
            pkey=campaign_id, 
            dowell_api_key=settings.PROJECT_API_KEY,
            workspace_id=workspace_id
        )
        campaign.launch(dowell_api_key=settings.PROJECT_API_KEY)

        return response.Response(
            data={
                "detail": "Campaign launched successfully."
            }, 
            status=status.HTTP_200_OK
        )
    



campaign_list_create_api_view = CampaignListCreateAPIView.as_view()
campaign_retreive_update_delete_api_view = CampaignRetrieveUpdateDeleteAPIView.as_view()
campaign_activate_deactivate_api_view = CampaignActivateDeactivateAPIView.as_view()
campaign_audience_list_add_api_view = CampaignAudienceListAddAPIView.as_view()
campaign_message_create_retrieve_api_view = CampaignMessageCreateRetreiveAPIView.as_view()
campaign_message_update_delete_api_view = CampaignMessageUpdateDeleteAPIView.as_view()
campaign_launch_api_view = CampaignLaunchAPIView.as_view()
user_registration_view = UserRegistrationView.as_view()
test_email_view = TestEmail.as_view()