FROM mcr.microsoft.com/dotnet/sdk:8.0
WORKDIR /app
RUN dotnet new console --framework net8.0 --no-restore && dotnet add package DocumentFormat.OpenXml --version 3.3.0
COPY Program.cs .
RUN dotnet publish -c Release -o /out --no-restore
ENTRYPOINT ["dotnet", "/out/app.dll"]
