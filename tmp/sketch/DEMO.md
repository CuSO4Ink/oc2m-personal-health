# Classroom Demonstration

Use sample information only. All labels below match the English application.

1. Select **Lin Chen · Patient** under **Demo role**.
2. Select **Add record**, enter a title, type, date, source and content, then choose **Save record**.
3. Select **View**. Use **Choose file** to attach a PDF or image if needed.
4. Select **Edit record**, change the content and choose **Save new version**. Show both versions under **Change history**.
5. Close the details and select **Share**. Choose **Dr. Wang** and **2 days**, then **Preview sharing** and **Confirm access**.
6. Switch to **Dr. Wang · Doctor**. Only the authorised report should be visible. Open it with **View**.
7. Switch back to **Lin Chen**. Under **Sharing**, choose **Revoke access** and confirm.
8. Switch back to **Dr. Wang**. The report is no longer listed under **Health records**. Under **Sharing**, select **Check blocked access** to demonstrate the denial.
9. Switch back to **Lin Chen** and open **Activity** to show successful access and the denied request.

For an expiry demonstration, grant access for **1 minute (expiry demo)**, wait for the permission to expire, and request access again. A doctor may need to refresh the list to update its displayed state; the backend checks validity on every request.

## Short progress statement

Over the past few days, we have built a working minimum viable product.
Users can add health records, upload files, edit records and review earlier versions.
They can give a doctor access to selected reports for a limited time.
The backend checks permissions every time a report or attachment is requested.
After access is revoked or expires, further requests are denied and recorded in the activity log.
We use sample data and demo roles at this stage. Real hospital integration and full account verification are still planned.

## Important distinction

This demonstration shows a working records-and-permissions workflow. It does not establish production identity verification, real hospital interoperability, clinical validity or readiness to process real patient information.
