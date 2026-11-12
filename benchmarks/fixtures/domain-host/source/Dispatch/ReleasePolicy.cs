namespace ParcelDesk;

public sealed record Clearance(
    bool WorkflowComplete, int CertificateRevision, int ApprovedRevision,
    bool Revoked, bool Express, bool[] Obligations);

public static class ReleasePolicy
{
    public static bool CanRelease(Clearance clearance)
    {
        return clearance.WorkflowComplete;
    }
}
